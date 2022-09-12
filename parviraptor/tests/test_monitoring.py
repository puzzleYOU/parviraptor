from unittest.mock import patch

from django.test import TestCase

from parviraptor.models import DummyJob
from parviraptor.monitoring import monitor_queue_entries


class MonitoringTests(TestCase):
    def test_does_not_complain_if_queue_is_empty(self):
        result = monitor_queue_entries([DummyJob])
        self.assertEqual(0, len(result))

    def test_complains_about_failed_jobs(self):
        with patch(
            "parviraptor.models.AbstractJob.count_failed_jobs",
            lambda: 1,
        ):
            result = monitor_queue_entries([DummyJob])
        self.assertEqual(1, len(result))

        self.assertEqual("DummyJob", result[0].queue_name)
        self.assertEqual(1, result[0].failed_jobs_count)
        self.assertEqual(0, result[0].long_processing_jobs_count)

    def test_complains_about_long_processing_jobs(self):
        with patch(
            "parviraptor.models.AbstractJob.count_long_processing_jobs",
            lambda: 1,
        ):
            result = monitor_queue_entries([DummyJob])
        self.assertEqual(1, len(result))

        self.assertEqual("DummyJob", result[0].queue_name)
        self.assertEqual(0, result[0].failed_jobs_count)
        self.assertEqual(1, result[0].long_processing_jobs_count)
