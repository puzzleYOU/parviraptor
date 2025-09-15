import logging
import signal
import threading
import traceback
from datetime import timedelta

from .exceptions import (
    DeferJob,
    IgnoreJob,
    InvalidJobError,
    TemporaryJobFailure,
    UnprocessableJob,
)
from .models.abstract import AbstractJob, BackoffStrategy, JobStatus

logger = logging.getLogger(__name__)

DEFAULT_TEMPORARY_FAILURE_THRESHOLD = 19


class QueueWorkerLogger:
    def __init__(self):
        self._counter = 0
        self._is_idle = False
        self._is_processable = True

    def info(self, *args, **kwargs):
        logger.info(*args, **kwargs)

    def debug(self, *args, **kwargs):
        logger.debug(*args, **kwargs)

    def mutate_to_processing_state(self):
        self._is_idle = False
        self._is_processable = True
        if self._counter == 0:
            self.info("processing jobs...")
        self._counter += 1

    def mutate_to_idle_state(self):
        if self._counter > 0 or not self._is_idle:
            self.info(f"processed {self._counter} jobs. awaiting new jobs.")
        self._is_idle = True
        self._counter = 0

    def mutate_to_unprocessable_state(self):
        if self._counter > 0 or self._is_processable:
            self.info(f"processed {self._counter} jobs so far.")
            self.info(
                "queue turned unprocessable right now. "
                "waiting until queue is processable again."
            )
        self._is_processable = False
        self._counter = 0


class JobWorker[TJob: AbstractJob]:
    def __init__(
        self,
        job: TJob,
        temporary_failure_threshold: int = DEFAULT_TEMPORARY_FAILURE_THRESHOLD,
    ):
        if job.status != JobStatus.PROCESSING:
            raise ValueError(f"expected job to be PROCESSING, got {job.status}")
        self.job = job
        self.temporary_failure_threshold = temporary_failure_threshold

    def process(self):
        try:
            self.job.process()
            self.job.status = JobStatus.PROCESSED
        except DeferJob as e:
            self._info(f"Deferring job: {e}")
            self.job.status = JobStatus.DEFERRED
            self.job.error_message = str(e)
        except IgnoreJob as e:
            self._info(f"Ignoring job: {e}")
            self.job.status = JobStatus.IGNORED
            self.job.error_message = str(e)
        except InvalidJobError as e:
            self._info(f"Invalid job: {e}")
            self.job.status = JobStatus.FAILED
            self.job.error_message = str(e)
            self._log_status()
        except TemporaryJobFailure as e:
            self._warn(f"temporary failure: {e}")
            self.job.error_count += 1
            if self.job.error_count > self.temporary_failure_threshold:
                msg = "error count reached threshold"
                self._error(msg)
                self.job.status = JobStatus.FAILED
                self.job.error_message = msg
                self._log_status()
            else:
                self.job.status = JobStatus.NEW
                # we intentionally reraise this failure because the retry
                # backoff handling is done beyond the scope of this context
                raise
        except Exception as e:
            logger.error(self._format_log_message(str(e)))
            logger.error(traceback.format_exc())
            self.job.status = JobStatus.FAILED
            self.job.error_message = str(e)
            self._log_status()
        finally:
            self.job.save()

    def _log_status(self):
        self._info(f"status={self.job.status}")

    def _info(self, message: str):
        logger.info(self._format_log_message(message))

    def _warn(self, message: str):
        logger.warning(self._format_log_message(message))

    def _error(self, message: str):
        logger.error(self._format_log_message(message))

    def _format_log_message(self, message: str) -> str:
        return f"{type(self.job).__name__} {self.job.pk}: {message}"


class QueueWorker[TJob: AbstractJob]:
    """Processing a certain job queue.

    Example:

    >>> worker = QueueWorker(DummyJob)
    >>> worker.run()  # blocks infinitely
    """

    def __init__(
        self,
        Job: type[TJob],
        pause_if_queue_empty=timedelta(minutes=1),
        temporary_failure_threshold=DEFAULT_TEMPORARY_FAILURE_THRESHOLD,
    ):
        self.Job = Job
        self.pause_if_queue_empty = pause_if_queue_empty
        self.temporary_failure_threshold = temporary_failure_threshold
        self.logger = QueueWorkerLogger()
        self._setup_signal_handling()
        self.current_job_worker: JobWorker[TJob] | None = None

    def run(self):
        while not self._caught_exit_signal.is_set():
            try:
                self.current_job_worker = self._get_next_job_and_update_status()
                self.logger.mutate_to_processing_state()
                self.current_job_worker.process()
            except self.Job.DoesNotExist:
                self.current_job_worker = None
                self.logger.mutate_to_idle_state()
                self._sleep(self.pause_if_queue_empty)
            except UnprocessableJob:
                self.logger.mutate_to_unprocessable_state()
                self._sleep(self.pause_if_queue_empty)
            except TemporaryJobFailure as e:
                # this would not be reraised if `error_count` was reached.
                # see JobWorker.
                minutes = self._calc_latency_in_minutes(e.error_count)
                self._sleep(timedelta(minutes=minutes))

    def _calc_latency_in_minutes(self, error_count: int) -> int:
        match self.Job.BACKOFF_STRATEGY:
            case BackoffStrategy.CONSTANT:
                return self.Job.BACKOFF_STEP_MINUTES
            case BackoffStrategy.EXPONENTIAL:
                return self.Job.BACKOFF_STEP_MINUTES ** min(error_count, 5)

    def _get_next_job_and_update_status(self) -> JobWorker[TJob]:
        job = self.Job.fetch_next_job()
        if job is None:
            raise self.Job.DoesNotExist()
        elif not job.is_processable():
            job.status = JobStatus.NEW
            job.save()
            raise UnprocessableJob()
        else:
            return JobWorker(
                job,
                temporary_failure_threshold=self.temporary_failure_threshold,
            )

    def _setup_signal_handling(self):
        self._caught_exit_signal = threading.Event()
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, self._exit_gracefully)

    def _exit_gracefully(self, signum, frame):
        self.logger.info(f"Exit signal caught. ({signal.Signals(signum).name})")
        self._caught_exit_signal.set()

    def _sleep(self, duration: timedelta):
        seconds = duration.total_seconds()
        self.logger.debug(f"... sleeping for {seconds}s")
        self._caught_exit_signal.wait(seconds)
