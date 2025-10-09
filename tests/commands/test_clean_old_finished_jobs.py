from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TransactionTestCase
from django.utils import timezone

from parviraptor.models.abstract import AbstractJob
from tests.models import DummyJob, DummyProductJob, IncrementCounterJob

COMMAND_MODULE = "parviraptor.management.commands.clean_old_finished_jobs"


class CleanOldFinishedJobsTests(TransactionTestCase):
    def test_can_process_all_queues(self):
        jobs = []

        def patched(Job: type[AbstractJob], _):
            self.assertEqual(7, Job.MAX_AGE_FOR_PROCESSED_JOBS_IN_DAYS)
            jobs.append(Job)

        with patch(f"{COMMAND_MODULE}._delete_old_finished_jobs", patched):
            self._call_command("--all-queues")

        self.assertCountEqual(
            [DummyJob, DummyProductJob, IncrementCounterJob], jobs
        )

    def test_can_process_single_queue(self):
        jobs = []

        def patched(Job: type[AbstractJob], _):
            self.assertEqual(7, Job.MAX_AGE_FOR_PROCESSED_JOBS_IN_DAYS)
            jobs.append(Job)

        with patch(f"{COMMAND_MODULE}._delete_old_finished_jobs", patched):
            self._call_command("--queue=tests.DummyJob")

        self.assertEqual([DummyJob], jobs)

    def test_leaves_unfinished_old_jobs_untouched(self):
        old_date = datetime.now(tz=timezone.utc) - timedelta(
            days=DummyJob.MAX_AGE_FOR_PROCESSED_JOBS_IN_DAYS
        )

        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="FAILED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.all().update(modification_date=old_date)
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")

        self.assertEqual(5, DummyJob.objects.count())
        self._call_command("--queue=tests.DummyJob")
        self.assertEqual(3, DummyJob.objects.count())

    def test_no_jobs_to_be_deleted(self):
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="FAILED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")

        self.assertEqual(5, DummyJob.objects.count())
        self._call_command("--queue=tests.DummyJob")
        self.assertEqual(5, DummyJob.objects.count())

    def test_can_delete_all_old_finished_jobs(self):
        old_date = datetime.now(tz=timezone.utc) - timedelta(
            days=DummyJob.MAX_AGE_FOR_PROCESSED_JOBS_IN_DAYS
        )

        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.all().update(modification_date=old_date)
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")

        self.assertEqual(5, DummyJob.objects.count())
        self._call_command("--queue=tests.DummyJob")
        self.assertEqual(2, DummyJob.objects.count())

    def test_chunked_deletion_removes_all_jobs(self):
        old_date = datetime.now(tz=timezone.utc) - timedelta(days=23)

        num_jobs = 2500
        for i in range(num_jobs):
            DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PENDING")
        DummyJob.objects.create(a=1, b=2, status="FAILED")
        DummyJob.objects.all().update(modification_date=old_date)

        self.assertEqual(num_jobs + 2, DummyJob.objects.count())

        self._call_command("--queue=tests.DummyJob")

        remaining_jobs = DummyJob.objects.exclude(status="PROCESSED")
        self.assertEqual(2, remaining_jobs.count())
        self.assertEqual(2, DummyJob.objects.count())

    def test_dry_run_prevents_deletion(self):
        old_date = datetime.now(tz=timezone.utc) - timedelta(
            days=DummyJob.MAX_AGE_FOR_PROCESSED_JOBS_IN_DAYS
        )

        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.all().update(modification_date=old_date)
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")
        DummyJob.objects.create(a=1, b=2, status="PROCESSED")

        self.assertEqual(5, DummyJob.objects.count())
        self._call_command("--queue=tests.DummyJob", "--dry-run")
        self.assertEqual(5, DummyJob.objects.count())

    def _call_command(self, *args):
        DEV_NULL = StringIO()
        call_command("clean_old_finished_jobs", *args, stdout=DEV_NULL)
