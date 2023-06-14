import logging
import signal
import threading  # nicht `from threading import Event` wg. `patch` im Test
import traceback
from datetime import timedelta

from django.db import transaction

from .exceptions import (
    DeferJob,
    IgnoreJob,
    InvalidJobError,
    TemporaryJobFailure,
)
from .models.abstract import AbstractJob

logger = logging.getLogger(__name__)
Status = AbstractJob.Status

DEFAULT_TEMPORARY_FAILURE_THRESHOLD = 16


class QueueWorker:
    """Abarbeitung einer Queue aus Job-Objekten.

    Der Worker stellt sicher, dass die Jobs in der Reihenfolge des Anlegens
    (FIFO) bearbeitet werden, und dass immer nur ein Job parallel in
    Bearbeitung ist. D.h. insbesondere, dass die komplette Queue steht, sobald
    ein Job fehlschlägt.

    Jedes Kind-Model von `parviraptor.models.AbstractJob` bildet
    eine eigene Queue, die wie folgt abgearbeitet werden kann
    (am Beispiel von `DummyJob`):

    >>> worker = QueueWorker(DummyJob)
    >>> worker.run()  # Endlosschleife

    Für mögliche Konfigurationsparameter siehe `__init__`.
    """

    def run(self):
        while not self._caught_exit_signal.is_set():
            try:
                job_worker = self._get_next_job_and_update_status()
                job_worker.process()
            except self.Job.DoesNotExist:
                self._sleep(self.pause_if_queue_empty)
            except TemporaryJobFailure as e:
                # Prüfung auf `error_count` befindet sich im `JobWorker`,
                # d.h. wir haben den Grenzwert noch nicht erreicht.
                latency = 2 ** min(e.error_count, 5)
                self._sleep(timedelta(minutes=latency))

    @transaction.atomic
    def _get_next_job_and_update_status(self):
        job = (
            self.Job.objects.select_for_update()
            .filter(status=Status.NEW)
            .order_by("id")
            .first()
        )
        if job is None:
            raise self.Job.DoesNotExist()
        else:
            job.status = Status.PROCESSING
            job.save()
            return JobWorker(
                job,
                temporary_failure_threshold=self.temporary_failure_threshold,
            )

    def __init__(
        self,
        Job,
        pause_if_queue_empty=timedelta(minutes=1),
        temporary_failure_threshold=DEFAULT_TEMPORARY_FAILURE_THRESHOLD,
    ):
        self.Job = Job
        self.pause_if_queue_empty = pause_if_queue_empty
        self.temporary_failure_threshold = temporary_failure_threshold
        self._setup_signal_handling()

    def _setup_signal_handling(self):
        self._caught_exit_signal = threading.Event()
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, self._exit_gracefully)

    def _exit_gracefully(self, signum, frame):
        logger.info(f"Exit signal caught. ({signal.Signals(signum).name})")
        self._caught_exit_signal.set()

    def _sleep(self, duration):
        logger.debug(f"... sleeping for {duration.seconds}s")
        self._caught_exit_signal.wait(duration.seconds)


class JobWorker:
    """Kontext für die Bearbeitung eines Jobs.

    Eine JobWorker-Instanz darf nur für einen Job mit Status PROCESSING
    erstellt werden und es darf nur eine solche Instanz für einen Job
    existieren.
    """

    def process(self):
        try:
            self._check_dependent_jobs()
            self.job.process()
            self._update_status(Status.PROCESSED)
            self._log_status()
        except DeferJob as e:
            self._info(f"Deferring job: {e}")
            self._update_status(Status.DEFERRED)
            self._set_error_message(str(e))
        except IgnoreJob as e:
            self._info(f"Ignoring job: {e}")
            self._update_status(Status.IGNORED)
            self._set_error_message(str(e))
        except InvalidJobError as e:
            self._info(f"Invalid job: {e}")
            self._update_status(Status.FAILED)
            self._set_error_message(str(e))
            self._log_status()
        except TemporaryJobFailure as e:
            self._warn(f"temporary failure: {e}")
            self._increment_error_count()
            if self.job.error_count > self.temporary_failure_threshold:
                msg = "error count reached threshold"
                self._error(msg)
                self._update_status(Status.FAILED)
                self._set_error_message(msg)
                raise ValueError(msg)
            else:
                self._update_status(Status.NEW)
                # Wir müssen den Fehler weiter werfen, da die Queue-Verarbeitung
                # eine gewisse Zeit pausieren soll, bevor der nächste Versuch
                # unternommen wird.
                raise
        except Exception as e:
            logger.error(self._format_log_message(str(e)))
            logger.error(traceback.format_exc())
            self._update_status(Status.FAILED)
            self._set_error_message(str(e))
            self._log_status()

    def __init__(
        self,
        job,
        temporary_failure_threshold=DEFAULT_TEMPORARY_FAILURE_THRESHOLD,
    ):
        assert job.status == Status.PROCESSING
        self.job = job
        self.temporary_failure_threshold = temporary_failure_threshold

    def _check_dependent_jobs(self):
        if (
            self.job.get_dependencies_queryset()
            .exclude(status=Status.PROCESSED)
            .exclude(status=Status.SQUASHED)
            .exclude(status=Status.IGNORED)
            .exclude(status=Status.DEFERRED)
            .count()
            > 0
        ):
            raise ValueError("not all dependent jobs were processed/squashed")

    def _update_status(self, new_status):
        self.job.status = new_status
        self.job.save()

    def _set_error_message(self, msg):
        self.job.error_message = msg
        self.job.save()

    def _increment_error_count(self):
        self.job.error_count += 1
        self.job.save()

    def _log_status(self):
        self._info(f"status={self.job.status}")

    def _info(self, message: str):
        logger.info(self._format_log_message(message))

    def _warn(self, message: str):
        logger.warning(self._format_log_message(message))

    def _error(self, message: str):
        logger.error(self._format_log_message(message))

    def _format_log_message(self, message: str):
        return f"{type(self.job).__name__} {self.job.id}: {message}"
