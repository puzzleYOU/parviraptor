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
    """Tests for `QueueWorker`.

    One problem when testing the worker is that `QueueWorker.run()` essentially
    generates an endless loop. To solve this, we patch `threading.Event` with
    `ExplodingEvent`, which will accept a defined number of `wait` calls, after
    which the QueueWorker will finish with a `MaxCallsReached` exception.


    By default, the pauses for "empty queue" (1s) and "temporary error" (100s)
    are configured (in `setUp`) to greatly differ in length and take the
    maximum wait number (9) into account. This allows you to use `assert_waits`
    to check exactly how often each case occurred.
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
        modification_date_before = job_a.modification_date  # one job is enough
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
        DummyJob.objects.create(a=0, b=1)  # fails five times
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

        # for traceability:
        temporary_failure_latency = 60 * (
            # increases exponentially for the first six errors
            2**0
            + 2**1
            + 2**2
            + 2**3
            + 2**4
            + 2**5
            # only constants from here on out
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
        job = DummyJob.objects.create(a=1, b=0)  # throws `ValueError`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(job.status, DummyJob.Status.FAILED)

    @disable_logging()
    def test_status_failed_on_invalidjoberror(self):
        job = DummyJob.objects.create(a=50, b=50)  # throws `InvalidJobError`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.FAILED, job.status)
        self.assertEqual("Ignoring result 100", job.error_message)

    @disable_logging()
    def test_status_ignored_on_ignorejob(self):
        job = DummyJob.objects.create(a=100, b=100)  # throws `IgnoreJob`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.IGNORED, job.status)
        self.assertEqual("Ignoring result 200", job.error_message)

    @disable_logging()
    def test_status_deferred_on_deferjob(self):
        job = DummyJob.objects.create(a=150, b=150)  # throws `DeferJob`
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.FAILED, job.status)
        self.assertEqual(
            "deferred retry threshold exceeded: Deferring result 300",
            job.error_message,
        )

    @disable_logging()
    def test_job_changes_get_saved_on_success_and_failure(self):
        # We cannot test saving in the case of temporary errors, since we must
        # abort processing of the queue before the job is processed
        # successfully. See `test_job_changes_get_saved_on_temporary_failure`
        job_a = DummyJob.objects.create(a=1, b=2)  # no error
        job_b = DummyJob.objects.create(a=2, b=0)  # error
        self.run_worker()
        for job in [job_a, job_b]:
            job.refresh_from_db()
            self.assertNotEqual(DummyJob.Status.NEW, job.status)
            self.assertNotEqual(None, job.result)

    @disable_logging()
    def test_fifo_depending_jobs_are_set_to_failed(self):
        job_a = DummyJob.objects.create(a=1, b=2)  # no error
        job_b = DummyJob.objects.create(a=1, b=0)  # error
        job_c = DummyJob.objects.create(a=1, b=2)  # c and d depend on job_b
        job_d = DummyJob.objects.create(a=1, b=2)  # → will also be 'FAILED'

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
        job = DummyJob.objects.create(a=0, b=2)  # temporary error
        self.run_worker()
        job.refresh_from_db()
        self.assertEqual(DummyJob.Status.NEW, job.status)
        self.assertEqual(2, job.result)

    @disable_logging()
    def test_sigterm_handling(self):
        job_a = DummyJob.objects.create(a=-1, b=-1)  # sends SIGTERM
        job_b = DummyJob.objects.create(a=1, b=2)
        self.run_worker()
        self.assert_waits(0, 0)

        # The first job was processed completely, as the signal-handling
        # only takes effect between jobs
        job_a.refresh_from_db()
        self.assertEqual(DummyJob.Status.PROCESSED, job_a.status)

        # The second job still has the status NEW:
        job_b.refresh_from_db()
        self.assertEqual(DummyJob.Status.NEW, job_b.status)
        self.assertEqual(None, job_b.result)

    def test_logging(self):
        logger = QueueWorkerLogger()
        with self.assertLogs() as cm:
            # no open jobs
            logger.mutate_to_idle_state()
            # processes 5 jobs
            for _ in range(5):
                logger.mutate_to_processing_state()

            # Only one information-log when there are no open jobs for a longer
            # period.
            # Since we log when processing a new job, we don't have to
            # constantly log "nothing to do" for periods without any jobs.
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            # processes 4 jobs again
            for _ in range(4):
                logger.mutate_to_processing_state()
            # no open jobs
            logger.mutate_to_idle_state()
            logger.mutate_to_idle_state()
            # not allowed to process more jobs
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            # processes one job
            logger.mutate_to_processing_state()
            # not allowed to process more jobs
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            logger.mutate_to_unprocessable_state()
            # no open jobs
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
    """mock object for `threading.Event`.

    Saves all calls to `wait` and throws `MaxCallsReached` when a defined number
    of calls is reached.
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
