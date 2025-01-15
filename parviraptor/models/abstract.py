import itertools
from datetime import datetime, timedelta, timezone
from functools import reduce
from typing import Any

from django.db import models
from django.db.models import Q

from parviraptor.exceptions import TemporaryJobFailure


class JobStatus(models.TextChoices):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    SQUASHED = "SQUASHED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"
    DEFERRED = "DEFERRED"


class AbstractJob(models.Model):
    """Basisklasse zum Bilden einer Job-Queue.

    Der einfachste Weg einen konkreten Job von dieser Basisklasse abzuleiten,
    ist der, von der abstrakten Klasse abzuleiten, die `AbstractJobFactory`
    erstellt.

    Für die abgeleitete Jobklasse gilt:
    - Die Werte hier für die `MAX_TIMEFRAME_...`-Konstanten sind Standardwerte
      und dürfen überschrieben werden, da kritische Grenzwerte z. B. für
      volllaufende Queues nicht zwingend allgemeingültig sind.
    """

    MAX_TIMEFRAME_FOR_JOB_PROCESSING_IN_MIN = 30
    MAX_TIMEFRAME_FOR_UNPROCESSED_JOBS_IN_MIN = 16 * 60

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
        """Bearbeitet den Job.

        Diese Methode muss in abgeleiteten konkreten Klassen implementiert
        werden. Die Verwaltung des Jobs (Status-Setzen auf PROCESSING usw.)
        und das Speichern des Jobs (auch im Fehlerfall) sind *nicht* Teil
        dieser Methode, das erfolgt außerhalb.

        Sollte es bei der Job-Verarbeitung zu einem Fehler kommen, muss in
        abgeleiteten `process()`-Methoden selbst ein entsprechender
        Rollback-Mechanismus implementiert werden
        (z. B. per `transaction.atomic`-Decorator oder Context-Manager).
        """
        raise NotImplementedError()

    def is_processable(self) -> bool:
        """Gibt zurück, ob die Queue verarbeitet werden kann.

        Die Standardimplementierung sieht vor, dass die Queue verarbeitet
        werden kann. Das kann in abgeleiteten Klassen überschrieben werden,
        um das Verarbeiten einer Queue unter bestimmten äußeren Umständen
        zu unterbinden. Diese Information ist für den übergeordneten Worker
        relevant.
        """
        return True

    @classmethod
    def fetch_next_job(cls, id_gt=None):
        job = cls._fetch_next_new_job(id_gt=id_gt)
        if job is None:
            raise cls.DoesNotExist()

        if cls.get_dependent_fields() is not None:
            # Hängt der aktuelle Job von Vorgängern ab, die FAILED sind, können
            # wir sofort den Job selbst und alle Nachfolger auf FAILED setzen.
            failed_predecessors = cls._fetch_failed_predecessors(job)
            cls._change_job_and_dependent_successors_to_failed_if_necessary(
                job, failed_predecessors
            )

            # Wenn Vorgänger noch nicht verarbeitet oder FAILED sind, dann
            # versuchen wir, den nächsten Job zu verarbeiten.
            if (
                cls._incomplete_predecessors_exist(job)
                or failed_predecessors.exists()
            ):
                return cls.fetch_next_job(id_gt=job.id)

        # Wir könnten selbst mit Transaktionen nicht verhindern, dass zwei
        # parallele Worker versuchen, denselben Job von NEW auf PROCESSING
        # zu setzen. Den Zustandsübergang per Table Locks zu sperren, macht
        # allerdings seitens Django an anderen Stellen Probleme.
        # Wenn `updated_jobs_count == 0` vorliegt, dann bedeutet das, dass
        # ein anderer Worker den Job bereits bearbeitet. In diesem Fall
        # machen wir einfach mit dem nächsten Job weiter.
        updated_jobs_count = cls.objects.filter(
            status=JobStatus.NEW, id=job.id
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
    def _fetch_next_new_job(cls, id_gt=None):
        jobs = cls.objects.filter(status=JobStatus.NEW)
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
        return [
            dict(zip(dependent_fields * len(dependent_fields), combination))
            for combination in combinations
        ]

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
        """Wirft einen temporären Fehler.

        Temporäre Fehler sind solche Fehler, die höchstwahrscheinlich bei
        einem erneuten Versuch nicht mehr auftreten. In `process()` sollte
        in solchen Fällen unbedingt diese Methode aufgerufen werden, damit
        der Job von außen neugestartet wird (solange ein gewisser Grenzwert
        an temporären Fehlschlägen nicht erreicht wird).
        """
        raise TemporaryJobFailure(message, self.error_count)

    class Meta:
        abstract = True


class AbstractJobFactory:
    """Factory für die Basisklasse einer Job-Queue.

    `dependent_fields` ist eine Liste an Feldnamen. Gibt es mehrere Jobs mit
    denselben Feldern, so müssen diese nach FIFO abgearbeitet werden. Das
    ermöglicht, Teilqueues innerhalb einer Queue zu haben.
    Ist `dependent_fields` leer, wird die Queue strikt nach FIFO abgearbeitet.

    "nach FIFO abgearbeitet" schließt ein, dass z. B. bei Fehlschlagen eines
    Jobs der nächste erst verarbeitet wird, wenn sein Vorgänger erfolgreich
    verarbeitet wurde.

    Ist `dependent_fields` None, so sind alle Jobs unabhängig voneinander und
    können in beliebiger Reihenfolge bearbeitet werden.

    Apps, die parviraptor verwenden, können konkrete Job-Klassen von der
    Basisklasse ableiten, die `make_base_class()` liefert. Auf diesem
    abgeleiteten Job können für diesen Job spezifische, weitere Model-Felder
    definiert werden. Ebenso können statische Felder auf dem Job überschrieben
    werden (näheres siehe in der Dokumentation von `AbstractJob` selbst).

    Die AbstractJobFactory ist Teil der Public API.
    """

    @classmethod
    def make_base_class(cls, dependent_fields: list[str] | None):
        class DerivedJob(AbstractJob):
            def __init_subclass__(cls):
                # `cls` ist ein abgeleiteter Job
                setattr(cls, "dependent_fields", dependent_fields)

            class Meta:
                abstract = True

        return DerivedJob
