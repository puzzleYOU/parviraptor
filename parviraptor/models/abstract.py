import enum
import itertools
from datetime import datetime, timedelta, timezone
from functools import reduce
from typing import Any

from django.db import models
from django.db.models import Q

from parviraptor.exceptions import TemporaryJobFailure


class JobStatus(models.TextChoices):
    NEW = "NEW"
    """
    Job is created and ready to be processed.
    """

    PROCESSING = "PROCESSING"
    """The job is currently being processed"""

    PROCESSED = "PROCESSED"
    """The job was successfully processed"""

    SQUASHED = "SQUASHED"
    """The job was squashed with one or more jobs"""

    FAILED = "FAILED"
    """
    Status will be set when the retry threshold is reached
    (retries > error_count) or when specific exceptions were raised.
    => see description of AbstractJob.process()
    """

    IGNORED = "IGNORED"
    """
    Job will be ignored for all upcoming runs.
    Manual interaction may be required!
    """

    DEFERRED = "DEFERRED"
    """Jobs will run after all 'NEW'-Jobs are run."""


@enum.unique
class BackoffStrategy(enum.Enum):
    EXPONENTIAL = enum.auto()
    CONSTANT = enum.auto()


class AbstractJob(models.Model):
    """Basisklasse zum Bilden einer Job-Queue.

    One should not directly derive from this class but use the base
    class inferred by `AbstractJobFactory`.

    Overridable class members:
    - MAX_TIMEFRAME_FOR_JOB_PROCESSING_IN_MIN
    - MAX_TIMEFRAME_FOR_JOB_UNPROCESSED_IN_MIN
    - BACKOFF_STEP_MINUTES
    - BACKOFF_STRATEGY
    """

    MAX_TIMEFRAME_FOR_JOB_PROCESSING_IN_MIN = 30
    MAX_TIMEFRAME_FOR_UNPROCESSED_JOBS_IN_MIN = 16 * 60

    BACKOFF_STEP_MINUTES = 2
    BACKOFF_STRATEGY = BackoffStrategy.EXPONENTIAL

    @classmethod
    def get_dependent_fields(cls):
        if not hasattr(cls, "dependent_fields"):
            raise AttributeError(
                f"{cls} is somehow misconfigured: "
                + "missing 'dependent_fields'"
            )
        return getattr(cls, "dependent_fields")

    Status = JobStatus

    creation_date = models.DateTimeField(
        auto_now_add=True,
    )
    modification_date = models.DateTimeField(
        auto_now=True,
    )
    status = models.CharField(
        choices=Status.choices,
        db_index=True,
        default=Status.NEW,
        max_length=32,
    )
    error_count = models.IntegerField(
        default=0,
    )
    error_message = models.TextField(
        blank=True,
        null=True,
    )

    def process(self):
        """Processes a job.

        Derived classes implement their concrete job logic here. This
        implementation does not have to care about concrete state
        transitions.

        One can raise any exception which cause a job to finalize to the
        `FAILED` state. Raising any `TemporaryJobFailure` triggers the
        job to be retried if it has not failed too often.

        In case job processing fails you might need to implement reasonable
        rollback mechanisms. For mutating database state, you might e.g.
        want to use `transaction.atomic` as decorator / context manager.
        """
        raise NotImplementedError()

    def on_job_terminated(self):
        pass

    def is_processable(self) -> bool:
        """Returns whether the job queue is processable.

        By default, it always returns True. This method may be overriden
        in case the processability of a certain job queue depends on
        runtime condition. If 'False' is returned, the job worker processing
        this job class will silently await until 'True' is returned again.
        """
        return True

    @classmethod
    def fetch_next_job(cls, id_gt=None, status=JobStatus.NEW):
        job = cls._fetch_next_job_by_status(id_gt=id_gt, status=status)
        if job is None:
            return None

        if cls.get_dependent_fields() is not None:
            # If current job depends on failed predecessors, we can set this
            # job and all of its successors to FAILED as well.
            failed_predecessors = cls._fetch_failed_predecessors(job)
            cls._change_job_and_dependent_successors_to_failed_if_necessary(
                job, failed_predecessors
            )

            # We try to process the next direct successor on incomplete or
            # failed predecessors as the next one might be processable.
            if (
                cls._incomplete_predecessors_exist(job)
                or failed_predecessors.exists()
            ):
                return cls.fetch_next_job(id_gt=job.id)

        # concurrency mitigation: two parallel workers might set the same job
        # to PROCESSING at the same time. `updated_jobs_count == 0` means
        # "another process already took care of this job". In this case we
        # can just silently continue.
        updated_jobs_count = cls.objects.filter(
            status=status, id=job.id
        ).update(
            status=JobStatus.PROCESSING,
            modification_date=datetime.now(tz=timezone.utc),
        )

        if updated_jobs_count == 1:
            job.status = JobStatus.PROCESSING
            return job
        elif updated_jobs_count == 0:
            return cls.fetch_next_job()
        else:
            raise RuntimeError()

    @classmethod
    def _fetch_next_job_by_status(cls, id_gt=None, status=JobStatus.NEW):
        jobs = cls.objects.filter(status=status)
        if id_gt is not None:
            jobs = jobs.filter(id__gt=id_gt)
        return jobs.order_by("id").first()

    @classmethod
    def _get_dependent_fields_lookup(cls, job):
        return reduce(
            lambda combined, field: combined
            & Q(**{field: getattr(job, field)}),
            cls.get_dependent_fields(),
            Q(),
        )

    @classmethod
    def _incomplete_predecessors_exist(cls, job):
        return cls.objects.filter(
            cls._get_dependent_fields_lookup(job),
            status__in=("NEW", "PROCESSING"),
            id__lt=job.id,
        ).exists()

    @classmethod
    def _fetch_failed_predecessors(cls, job):
        return cls.objects.filter(
            cls._get_dependent_fields_lookup(job),
            status="FAILED",
            id__lt=job.id,
        )

    @classmethod
    def _change_job_and_dependent_successors_to_failed_if_necessary(
        cls, job, failed_predecessors
    ):
        if failed_predecessors.exists():
            cls.objects.filter(
                cls._get_dependent_fields_lookup(job),
                id__gte=job.id,
            ).update(
                status="FAILED",
                error_message="dependent jobs failed",
            )

    @classmethod
    def get_queryset_filters_for_disjoint_queues(
        cls,
    ) -> list[dict[str, Any]]:
        dependent_fields = cls.get_dependent_fields()
        if dependent_fields is None:
            return []
        combinations = itertools.product(
            *[
                set(cls.objects.values_list(field, flat=True))
                for field in dependent_fields
            ]
        )
        filters = [
            dict(zip(dependent_fields, combination))
            for combination in combinations
        ]
        return filters

    @classmethod
    def count_failed_jobs(cls) -> int:
        return cls.objects.filter(status=cls.Status.FAILED).count()

    @classmethod
    def count_long_processing_jobs(cls) -> int:
        dt = datetime.now(tz=timezone.utc) - timedelta(
            minutes=cls.MAX_TIMEFRAME_FOR_JOB_PROCESSING_IN_MIN
        )

        return cls.objects.filter(
            status=cls.Status.PROCESSING,
            modification_date__lt=dt,
        ).count()

    @classmethod
    def count_long_unprocessed_jobs(cls) -> int:
        dt = datetime.now(tz=timezone.utc) - timedelta(
            minutes=cls.MAX_TIMEFRAME_FOR_UNPROCESSED_JOBS_IN_MIN
        )

        return cls.objects.filter(
            status=cls.Status.NEW,
            creation_date__lt=dt,
        ).count()

    def raise_temporary_failure(self, message: str):
        """Raises a temporary failure.

        Temporary failures are such which might not occur after one or more
        retries. `process()` should call this method so the job can be resumed
        by the worker in case the temporary failure threshold has not been
        exceeded.
        """
        raise TemporaryJobFailure(message, self.error_count)

    class Meta:
        abstract = True


class AbstractJobFactory:
    """Factory for inferring job queue base classes.

    `dependent_fields` is a list of model field names. If there are multiple
    jobs with the same field values, they are processed by FIFO strategy. This
    enables for disjoint queues within one queue model.

    - `dependent_fields = []` declares a strict FIFO queue.
    - `dependent_fields = None` means all jobs can be processed from each
      other independently.

    "FIFO strategy" also covers that successors with same `dependent_fields`
    values are only processed if all pending predecessors have been
    *successfully* completed.
    """

    @classmethod
    def make_base_class(
        cls, dependent_fields: list[str] | None
    ) -> type[AbstractJob]:
        class DerivedJob(AbstractJob):
            def __init_subclass__(cls):
                # `cls` is a derived class
                setattr(cls, "dependent_fields", dependent_fields)

            class Meta(AbstractJob.Meta):
                abstract = True

        return DerivedJob
