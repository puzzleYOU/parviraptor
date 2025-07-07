import logging
from contextlib import contextmanager
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from parviraptor.worker import QueueWorker

logger = logging.getLogger(__name__)


@contextmanager
def queue_worker_mock(log):
    run = QueueWorker.run
    QueueWorker.run = lambda *x, **y: logger.debug(log)
    yield
    QueueWorker.run = run


class ProcessQueueTestCase(TestCase):
    def test_process_queue(self):
        log = "Are you mocking me?"
        # QueueWorker.run wird in test_queue getestet
        with queue_worker_mock(log):
            # nicht existierendes Model
            out = StringIO()
            self.assertRaises(
                LookupError,
                lambda: call_command(
                    "process_queue",
                    ["tests", "NoneExistingModel"],
                    stdout=out,
                ),
            )
            self.assertNotIn("QueueWorker for", out.getvalue())

            # existierendes Model
            out = StringIO()
            with self.assertLogs(logger="", level="DEBUG") as cm:
                call_command("process_queue", ["tests", "DummyJob"], stdout=out)
            self.assertIn("QueueWorker for DummyJob", out.getvalue())
            # prüfen, dass QueueWorker.run auch wirklich aufgerufen wird
            self.assertIn(log, cm.output[0])
