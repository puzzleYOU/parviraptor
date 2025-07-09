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
        """Processes a queue, optionally in parallel.

        If `number_of_threads >= 1`, they are parallelized using threads.

        This method creates the given job instances and ensures that in the end
        they are successfully processed.
        It does NOT block infinitely as the standard queue processor would do.
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

        threads = [QueueWorkerThread() for _ in range(number_of_threads)]
        # join() blocks the current thread, this is why we need separate loops
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

    def get_ordered_ids(self, qs, field):
        return [job.pk for job in qs.order_by(field)]
