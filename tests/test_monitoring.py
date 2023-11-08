from unittest.mock import patch

from django.test import TestCase

from parviraptor.monitoring import monitor_queue_entries

from .models import DummyJob


class MonitoringTests(TestCase):
    def test_does_not_complain_if_queue_is_empty(self):
        result = monitor_queue_entries([DummyJob])
        self.assertEqual(0, len(result))

    def test_complains_about_failed_jobs(self):
        with patch(
            "tests.models.DummyJob.count_failed_jobs",
            lambda: 1,
        ):
            result = monitor_queue_entries([DummyJob])
        self.assertEqual(1, len(result))

        self.assertEqual("DummyJob", result[0].queue_name)
        self.assertEqual(1, result[0].failed_jobs_count)
        self.assertEqual(0, result[0].long_processing_jobs_count)
        self.assertEqual(0, result[0].long_unprocessed_jobs_count)

    def test_complains_about_long_processing_jobs(self):
        with patch(
            "tests.models.DummyJob.count_long_processing_jobs",
            lambda: 1,
        ):
            result = monitor_queue_entries([DummyJob])
        self.assertEqual(1, len(result))

        self.assertEqual("DummyJob", result[0].queue_name)
        self.assertEqual(0, result[0].failed_jobs_count)
        self.assertEqual(1, result[0].long_processing_jobs_count)
        self.assertEqual(0, result[0].long_unprocessed_jobs_count)

    def test_complains_about_long_unprocessed_jobs(self):
        with patch(
            "tests.models.DummyJob.count_long_unprocessed_jobs",
            lambda: 1,
        ):
            result = monitor_queue_entries([DummyJob])
        self.assertEqual(1, len(result))

        self.assertEqual("DummyJob", result[0].queue_name)
        self.assertEqual(0, result[0].failed_jobs_count)
        self.assertEqual(0, result[0].long_processing_jobs_count)
        self.assertEqual(1, result[0].long_unprocessed_jobs_count)

    def test_flexible_long_unprocessed_timeframe(self):
        DummyJob.objects.create(a=1, b=2)
        self.assertEqual([], monitor_queue_entries([DummyJob]))
        with patch(
            "tests.models.DummyJob.MAX_TIMEFRAME_FOR_UNPROCESSED_JOBS_IN_MIN",
            -1,
        ):
            self.assertEqual(
                1, self._first_monitoring_entry.long_unprocessed_jobs_count
            )

    def test_flexible_long_processing_timeframe(self):
        DummyJob.objects.create(a=1, b=2, status="PROCESSING")
        self.assertEqual([], monitor_queue_entries([DummyJob]))
        with patch(
            "tests.models.DummyJob.MAX_TIMEFRAME_FOR_JOB_PROCESSING_IN_MIN", -1
        ):
            self.assertEqual(
                1, self._first_monitoring_entry.long_processing_jobs_count
            )

    @property
    def _first_monitoring_entry(self):
        result = monitor_queue_entries([DummyJob])
        self.assertEqual(1, len(result))
        return result[0]
