import traceback
from threading import Thread
from typing import Iterable

from django.test import TransactionTestCase

from ..models.abstract import AbstractJob
from .worker import InfinityLoopFreeQueueWorker


class QueueTestCase(TransactionTestCase):
    def process_queue(
        self,
        JobClass: type,
        jobs: Iterable[AbstractJob],
        number_of_threads: int,
        create_jobs: bool = True,
    ):
        """Verarbeitet eine Queue mit `number_of_threads` parallelen Threads.

        Die Funktion legt die übergebenen `jobs` an und stellt sicher, dass sie
        am Ende alle `PROCESSED` sind.
        Der aufrufende Test muss sich nicht darum bemühen, den Worker per z. B.
        `SIGTERM` zu beenden, das erfolgt intern von selbst.
        """
        jobs = list(jobs)
        if create_jobs:
            JobClass.objects.bulk_create(jobs)
        self.assertEqual(
            (len(jobs), 0, 0, 0),
            (
                JobClass.objects.filter(status="NEW").count(),
                JobClass.objects.filter(status="PROCESSING").count(),
                JobClass.objects.filter(status="PROCESSED").count(),
                JobClass.objects.filter(status="FAILED").count(),
            ),
        )

        if number_of_threads == 1:
            InfinityLoopFreeQueueWorker(JobClass).run()
        else:
            self._process_concurrently(JobClass, number_of_threads)

        self.assertEqual(
            (0, 0, len(jobs), 0),
            (
                JobClass.objects.filter(status="NEW").count(),
                JobClass.objects.filter(status="PROCESSING").count(),
                JobClass.objects.filter(status="PROCESSED").count(),
                JobClass.objects.filter(status="FAILED").count(),
            ),
        )

    def _process_concurrently(self, JobClass, number_of_threads):
        class QueueWorkerThread(Thread):
            def __init__(self):
                super().__init__()
                self.succeeded = False
                self.failure_detail = None

            def run(self):
                try:
                    InfinityLoopFreeQueueWorker(JobClass).run()
                    self.succeeded = True
                except Exception as ex:
                    print(traceback.format_exc())
                    self.failure_detail = f"{type(ex).__name__}: {ex}"

        threads = [QueueWorkerThread() for _ in range(0, number_of_threads)]
        # start() und join() dürfen nicht in derselben Schleife ausgeführt
        # werden, weil join() den aktuellen Thread blockiert. Man muss also
        # erst alle Threads starten und dann erst auf alle warten.
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for idx, thread in enumerate(threads):
            if not thread.succeeded:
                if thread.failure_detail:
                    self.fail(
                        f"thread #{idx} failed with {thread.failure_detail}"
                    )
                else:
                    self.fail(f"thread #{idx} was however not processed")
