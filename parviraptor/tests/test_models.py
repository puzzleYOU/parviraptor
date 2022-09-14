from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from .models import DummyJob


class AbstractJobTests(TestCase):
    """
    Die Tests hier beziehen sich auf Funktionalität des `AbstractJob`.
    Da der `AbstractJob` bekanntlich ein abstraktes Model ist,
    nutzen wir den `DummyJob` zum Testen.
    """

    def test_count_failed_jobs(self):
        self.assertEqual(0, DummyJob.count_failed_jobs())
        job = DummyJob.objects.create(a=1, b=1)
        self.assertEqual(0, DummyJob.count_failed_jobs())
        job.status = DummyJob.Status.FAILED
        job.save()
        self.assertEqual(1, DummyJob.count_failed_jobs())

    def test_count_long_processing_jobs_(self):
        self.assertEqual(0, DummyJob.count_long_processing_jobs())

        job = DummyJob.objects.create(a=1, b=1)
        self.assertEqual(0, DummyJob.count_long_processing_jobs())

        DummyJob.objects.filter(pk=job.id).update(
            status=DummyJob.Status.PROCESSING
        )
        self.assertEqual(0, DummyJob.count_long_processing_jobs())

        DummyJob.objects.filter(pk=job.id).update(
            modification_date=datetime(
                2000,
                1,
                1,
                13,
                37,
                42,
                tzinfo=timezone.utc,
            )
        )
        self.assertEqual(1, DummyJob.count_long_processing_jobs())
