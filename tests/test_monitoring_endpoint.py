import re
from unittest.mock import patch

from django.test import TestCase


class MonitoringEndpointTests(TestCase):
    def request_monitoring_endpoint(self):
        resp = self.client.get("/queue-monitoring/")
        content = resp.content.decode()
        normalized = re.sub(r"\s+", " ", content).strip()
        return normalized

    def test_does_not_complain_if_queue_is_empty(self):
        self.assertEqual("<p>Alles OK</p>", self.request_monitoring_endpoint())

    def test_complains_about_failed_jobs(self):
        with patch(
            "tests.models.DummyJob.count_failed_jobs",
            lambda: 1,
        ):
            self.assertEqual(
                "<p> There are 1 failed, 0 long processing and 0 long "
                "unprocessed DummyJobs. </p>",
                self.request_monitoring_endpoint(),
            )

    def test_complains_about_long_processing_jobs(self):
        with patch(
            "tests.models.DummyJob.count_long_processing_jobs",
            lambda: 1,
        ):
            self.assertEqual(
                "<p> There are 0 failed, 1 long processing and 0 long "
                "unprocessed DummyJobs. </p>",
                self.request_monitoring_endpoint(),
            )

    def test_complains_about_long_unprocessed_jobs(self):
        with patch(
            "tests.models.DummyJob.count_long_unprocessed_jobs",
            lambda: 1,
        ):
            self.assertEqual(
                "<p> There are 0 failed, 0 long processing and 1 long "
                "unprocessed DummyJobs. </p>",
                self.request_monitoring_endpoint(),
            )
