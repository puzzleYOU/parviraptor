import os
import subprocess
import time
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from parviraptor.worker import QueueWorker, QueueWorkerLogger

from .models import DummyJob
from .utils import disable_logging


class QueueTestCase(TestCase):
    """Tests für `QueueWorker`.

    Ein Problem beim Testen des Workers ist, dass `QueueWorker.run()` im
    Wesentlichen eine Endlosschleife ist. Dazu patch-en wir `threading.Event`
    mit `ExplodingEvent`, damit nur eine definierte Anzahl an `wait`-Aufrufen
    möglich ist und danach der QueueWorker durch eine
    `MaxCallsReached`-Exception beendet wird.

    Standardmäßig (in `setUp`) werden die Pausen für "leere Queue" (1s) und
    "temporärer Fehler" (100s) stark voneinander abweichend konfiguriert,
    v.a. unter Berücksichtigung der maximalen Wait-Zahl (9). Das ermöglicht mit
    `assert_waits` exakt zu prüfen, wie oft welcher Fall aufgetreten ist.
    """

    def setUp(self):
        self.pause_if_queue_empty = timedelta(seconds=1)
        self.max_wait_calls = 9

    def test_sleep_if_queue_empty(self):
        self.run_worker()
        self.assert_waits(10, 0)

    def test_sleep_if_queue_only_contains_squashed_and_processed(self):
        DummyJob.objects.create(a=0, b=0, status=DummyJob.Status.PROCESSED)
        DummyJob.objects.create(a=0, b=0, status=DummyJob.Status.SQUASHED)
        DummyJob.objects.create(a=0, b=0, status=DummyJob.Status.SQUASHED)
        DummyJob.objects.create(a=0, b=0, status=DummyJob.Status.PROCESSED)
        self.run_worker()
        self.assert_waits(10, 0)

    @disable_logging()
    def test_successful_processing(self):
        job_a = DummyJob.objects.create(a=1, b=2)
        job_b = DummyJob.objects.create(a=3, b=7)

        self.run_worker()
        modification_date_before = job_a.modification_date  # ein Job reicht
        job_a.refresh_from_db()
        job_b.refresh_from_db()
        modification_date_after = job_a.modification_date
        self.assertGreater(modification_date_after, modification_date_before)

        self.assertEqual(job_a.status, DummyJob.Status.PROCESSED)
        self.assertEqual(job_a.result, 3)
        self.assertEqual(job_b.status, DummyJob.Status.PROCESSED)
        self.assertEqual(job_b.result, 10)

    @disable_logging()
    def test_retry_on_temporary_failure(self):
        DummyJob.objects.create(a=0, b=1)  # schlägt fünf Mal fehl
        self.run_worker()
        job = DummyJob.objects.get()
        self.assertEqual(5, job.error_count)
        self.assertEqual(1, job.result)
        self.assertIsNone(job.error_message)
        self.assertEqual(DummyJob.Status.PROCESSED, job.status)
        self.assert_waits(5, 5)

    @disable_logging()
    def test_exceed_temporary_failure_threshold(self):
        self.max_wait_calls = 20
        DummyJob.objects.create(a=0, b=100000)
        self.run_worker()  # always fails temporarily
        job = DummyJob.objects.get()
        self.assertEqual(20, job.error_count)
        self.assertIsNone(job.result)
        self.assertEqual(DummyJob.Status.FAILED, job.status)

    @disable_logging()
    def test_deferred_threshold(self):
        self.max_wait_calls = 20
        DummyJob.objects.create(a=0, b=300)
        self.run_worker()
        job = DummyJob.objects.get()
        self.assertEqual(20, job.error_count)
        self.assertEqual(DummyJob.Status.FAILED, job.status)

    @disable_logging()
    def test_retry_on_not_processable(self):
        DummyJob.objects.create(a=0, b=1)
        with patch.object(DummyJob, "is_processable", lambda self: False):
            self.run_worker()
        job = DummyJob.objects.get()
        self.assertEqual(DummyJob.Status.NEW, job.status)
        self.assertEqual(0, job.error_count)
        self.assertIsNone(job.result)
        self.assert_waits(10, 0)

    @disable_logging()
    def test_retry_on_temporary_failure_calculates_backoff_properly(self):
        self.pause_if_queue_empty = timedelta(seconds=0)

        with patch("tests.models.MAX_ERROR_COUNT", 10):
            DummyJob.objects.create(a=0, b=1)
            self.run_worker()

        job = DummyJob.objects.get()
        self.assertEqual(10, job.error_count)
        self.assertEqual(1, job.result)
        self.assert_waits(0, 10)

        # Zur Nachvollziehbarkeit:
        temporary_failure_latency = 60 * (
            # die ersten 6 Fehlschläge geht es exponentiell hoch
            2**0
            + 2**1
            + 2**2
            + 2**3
            + 2**4
            + 2**5
            # ab jetzt aber nur noch konstant
            + 2**5
            + 2**5
            + 2**5
            + 2**5
        )

        self.assertEqual(
            temporary_failure_latency,
            self.exploding_event.total_wait_timeouts,
        )

    @disable_logging()
    def test_status_failed_on_exception(self):
        job = DummyJob.objects.create(a=1, b=0)  # wirft `ValueError`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(job.status, DummyJob.Status.FAILED)

    @disable_logging()
    def test_status_failed_on_invalidjoberror(self):
        job = DummyJob.objects.create(a=50, b=50)  # wirft `InvalidJobError`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.FAILED, job.status)
        self.assertEqual("Ignoring result 100", job.error_message)

    @disable_logging()
    def test_status_ignored_on_ignorejob(self):
        job = DummyJob.objects.create(a=100, b=100)  # wirft `IgnoreJob`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.IGNORED, job.status)
        self.assertEqual("Ignoring result 200", job.error_message)

    @disable_logging()
    def test_status_deferred_on_deferjob(self):
        job = DummyJob.objects.create(a=150, b=150)  # wirft `DeferJob`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.FAILED, job.status)
        self.assertEqual(
            "deferred retry threshold exceeded: Deferring result 300",
            job.error_message,
        )

    @disable_logging()
    def test_job_changes_get_saved_on_success_and_failure(self):
        # Wir können das Speichern bei temporären Fehlern nicht testen, da wir
        # die Queue-Verarbeitung abbrechen müssen, bevor der Job erfolgreich
        # verarbeitet wird. Siehe
        # `test_job_changes_get_saved_on_temporary_failure`.
        job_a = DummyJob.objects.create(a=1, b=2)  # keine Fehler
        job_b = DummyJob.objects.create(a=2, b=0)  # Fehler
        self.run_worker()
        for job in [job_a, job_b]:
            job.refresh_from_db()
            self.assertNotEqual(DummyJob.Status.NEW, job.status)
            self.assertNotEqual(None, job.result)

    @disable_logging()
    def test_fifo_depending_jobs_are_set_to_failed(self):
        job_a = DummyJob.objects.create(a=1, b=2)  # keine Fehler
        job_b = DummyJob.objects.create(a=1, b=0)  # Fehler
        job_c = DummyJob.objects.create(a=1, b=2)  # c und d hängen von job_b ab
        job_d = DummyJob.objects.create(a=1, b=2)  # → werden dann auch FAILED

        for job in [job_a, job_b, job_c, job_d]:
            job.refresh_from_db()
            self.assertEqual(DummyJob.Status.NEW, job.status)
        self.run_worker()
        for job in [job_a, job_b, job_c, job_d]:
            job.refresh_from_db()
        self.assertEqual(DummyJob.Status.PROCESSED, job_a.status)
        self.assertEqual(DummyJob.Status.FAILED, job_b.status)
        self.assertEqual("b cannot be 0", job_b.error_message)
        self.assertEqual(DummyJob.Status.FAILED, job_c.status)
        self.assertEqual("dependent jobs failed", job_c.error_message)
        self.assertEqual(DummyJob.Status.FAILED, job_d.status)
        self.assertEqual("dependent jobs failed", job_d.error_message)

    @disable_logging()
    def test_job_changes_get_saved_on_temporary_failure(self):
        self.max_wait_calls = 0
        job = DummyJob.objects.create(a=0, b=2)  # temporärer Fehler
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.NEW, job.status)
        self.assertEqual(2, job.result)

    @disable_logging()
    def test_sigterm_handling(self):
        job_a = DummyJob.objects.create(a=-1, b=-1)  # sendet SIGTERM
        job_b = DummyJob.objects.create(a=1, b=2)
        self.run_worker()
        self.assert_waits(0, 0)

        # Der erste Job wurde vollständig verarbeitet, da das Signal-Handling
        # immer nur zwischen Jobs greift.
        job_a.refresh_from_db()
        self.assertEqual(DummyJob.Status.PROCESSED, job_a.status)

        # Der zweite Job hat immer noch den Status NEW:
        job_b.refresh_from_db()
        self.assertEqual(DummyJob.Status.NEW, job_b.status)
        self.assertEqual(None, job_b.result)

    def test_logging(self):
        logger = QueueWorkerLogger()
        with self.assertLogs() as cm:
            # keine Jobs offen
            logger.mutate_to_idle_state()
            # verarbeitet 5 Jobs
            for _ in range(5):
                logger.mutate_to_processing_state()
            # Für längere Zeit keine Jobs mehr offen ergibt nur 1 Meldung.
            # Dadurch dass wir explizit loggen, wenn wir wieder Jobs
            # verarbeiten, müssen wir "es ist nichts zu tun" nicht ständig
            # loggen in längeren Leerlaufphasen.
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            # verarbeitet nochmal 4 Jobs
            for _ in range(4):
                logger.mutate_to_processing_state()
            # keine Jobs mehr offen
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            # darf keine Jobs mehr verarbeiten
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            # verarbeitet einen Job
            logger.mutate_to_processing_state()
            # darf keine Jobs mehr verarbeiten
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            # keine Jobs mehr offen
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
        self.assertEqual(
            [
                "processed 0 jobs. awaiting new jobs.",
                "processing jobs...",
                "processed 5 jobs. awaiting new jobs.",
                "processing jobs...",
                "processed 4 jobs. awaiting new jobs.",
                "processed 0 jobs so far.",
                "queue turned unprocessable right now. "
                + "waiting until queue is processable again.",
                "processing jobs...",
                "processed 1 jobs so far.",
                "queue turned unprocessable right now. "
                + "waiting until queue is processable again.",
                "processed 0 jobs. awaiting new jobs.",
            ],
            [record.message for record in cm.records],
        )

    @disable_logging()
    def test_sigterm_interrupts_sleep(self):
        with self.assert_max_runtime(timedelta(seconds=2)):
            self.delayed_send_sigterm(os.getpid(), timedelta(seconds=1))
            worker = QueueWorker(
                DummyJob, pause_if_queue_empty=timedelta(seconds=3)
            )
            worker.run()

    @disable_logging()
    def test_sigint_interrupts_sleep(self):
        with self.assert_max_runtime(timedelta(seconds=2)):
            self.delayed_send_sigint(os.getpid(), timedelta(seconds=1))
            worker = QueueWorker(
                DummyJob, pause_if_queue_empty=timedelta(seconds=3)
            )
            worker.run()

    @contextmanager
    def assert_max_runtime(self, max_runtime):
        t0 = time.time()
        yield
        t1 = time.time()
        self.assertLessEqual(t1 - t0, max_runtime.seconds)

    def delayed_send_sigterm(self, pid, delay):
        subprocess.Popen(["sh", "-c", f"sleep {delay.seconds} && kill {pid}"])

    def delayed_send_sigint(self, pid, delay):
        subprocess.Popen(
            ["sh", "-c", f"sleep {delay.seconds} && kill -2 {pid}"]
        )

    def run_worker(self):
        with self.exploding_event():
            self.worker = QueueWorker(
                DummyJob,
                pause_if_queue_empty=self.pause_if_queue_empty,
            )
            try:
                self.worker.run()
            except MaxCallsReached:
                pass

    @contextmanager
    def exploding_event(self):
        self.exploding_event = ExplodingEvent(self.max_wait_calls)
        with patch("threading.Event", lambda: self.exploding_event):
            yield

    def assert_waits(self, empty_queue_count, temporary_failure_count):
        temporary_failure_latency = 60 * sum(
            [2 ** min(x, 5) for x in range(temporary_failure_count)]
        )

        expected = (
            empty_queue_count * self.pause_if_queue_empty.seconds
            + temporary_failure_latency
        )
        self.assertEqual(expected, self.exploding_event.total_wait_timeouts)


class ExplodingEvent:
    """Mock-Objekt für `threading.Event`.

    Speichert alle Aufrufe von `wait` und wirft `MaxCallsReached`, sobald eine
    festgelegte Zahl an Aufrufen erfolgt ist.
    """

    def __init__(self, max_waits):
        self.flag = False
        self.max_waits = max_waits
        self.wait_timeouts = []

    def is_set(self):
        return self.flag

    def set(self):
        self.flag = True

    def clear(self):
        self.flag = False

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout if timeout is not None else 0)
        if len(self.wait_timeouts) > self.max_waits:
            raise MaxCallsReached("wait()", self.wait_timeouts)

    @property
    def total_wait_timeouts(self):
        return sum(self.wait_timeouts)


class MaxCallsReached(Exception):
    def __init__(self, name, calls):
        super().__init__(f"{name} was called too often: {len(calls)} times")
