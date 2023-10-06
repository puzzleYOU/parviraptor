from threading import Thread
from typing import Iterable

from django.test import TransactionTestCase

from ..models import AbstractJob
from .worker import InfinityLoopFreeQueueWorker


class QueueTestCase(TransactionTestCase):
    def process_queue(
        self,
        JobClass: type,
        jobs: Iterable[AbstractJob],
        number_of_threads: int,
    ):
        """Verarbeitet eine Queue mit `number_of_threads` parallelen Threads.

        Die Funktion legt die übergebenen `jobs` an und stellt sicher, dass sie
        am Ende alle `PROCESSED` sind.
        Der aufrufende Test muss sich nicht darum bemühen, den Worker per z. B.
        `SIGTERM` zu beenden, das erfolgt intern von selbst.
        """
        jobs = list(jobs)
        JobClass.objects.bulk_create(jobs)
        self.assertEqual(
            (len(jobs), 0, 0, 0),
            (
                JobClass.objects.filter(status="NEW").count(),
                JobClass.objects.filter(status="PROCESSING").count(),
                JobClass.objects.filter(status="PROCESSED").count(),
                JobClass.objects.filter(status="FAILED").count(),
            )
        )
        threads = [
            Thread(target=lambda: InfinityLoopFreeQueueWorker(JobClass).run())
            for _ in range(0, number_of_threads)
        ]

        # start() und join() dürfen nicht in derselben Schleife ausgeführt
        # werden, weil join() den aktuellen Thread blockiert. Man muss also
        # erst alle Threads starten und dann erst auf alle warten.
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(
            (0, 0, len(jobs), 0),
            (
                JobClass.objects.filter(status="NEW").count(),
                JobClass.objects.filter(status="PROCESSING").count(),
                JobClass.objects.filter(status="PROCESSED").count(),
                JobClass.objects.filter(status="FAILED").count(),
            )
        )
