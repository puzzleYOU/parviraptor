import logging
from datetime import datetime, timedelta, timezone

from django.apps import apps
from django.core.management.base import BaseCommand, CommandParser

from parviraptor.models.abstract import AbstractJob
from parviraptor.utils import enumerate_job_models, iter_chunks

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cleans up obsolete finished jobs"

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                """
                print which jobs would be deleted instead of actually
                deleting them
                """
            ),
        )
        queue_switch = parser.add_mutually_exclusive_group()
        queue_switch.add_argument(
            "--all-queues",
            action="store_true",
            help=(
                """
                Removes old finished jobs in all job models existing
                within the current installation.
                """
            ),
        )
        queue_switch.add_argument(
            "--queue",
            type=str,
            help="<app_label>.<ModelName>, e.g. my_app.SomeRandomJob",
        )

    def handle(self, **options):
        self.dry_run = options["dry_run"]
        self._handle(**options)

    def _handle(self, **options):
        relevant_job_models: list[type[AbstractJob]] = (
            enumerate_job_models()
            if options["all_queues"]
            else [_load_model_from_fully_qualified_name(options["queue"])]
        )
        for Job in relevant_job_models:
            if Job.MAX_AGE_FOR_PROCESSED_JOBS_IN_DAYS is not None:
                _delete_old_finished_jobs(Job, self.dry_run)


def _delete_old_finished_jobs(Job: type[AbstractJob], dry_run: bool = False):
    border = datetime.now(tz=timezone.utc) - timedelta(
        days=Job.MAX_AGE_FOR_PROCESSED_JOBS_IN_DAYS
    )
    old_jobs = Job.objects.filter(
        modification_date__lte=border, status="PROCESSED"
    )
    _delete_in_chunks(Job, old_jobs, dry_run)


def _delete_in_chunks(Job: type[AbstractJob], jobs, dry_run: bool = False):
    pks = jobs.values_list("pk", flat=True)
    pks_count = pks.count()

    CHUNK_SIZE = 2_000
    full_chunks = pks_count // CHUNK_SIZE
    remainder = 0 if pks_count % CHUNK_SIZE == 0 else 1
    chunk_count = full_chunks + remainder

    logger.info(f"{Job.__name__}: Process {pks_count} jobs...")
    for i, chunk in enumerate(iter_chunks(CHUNK_SIZE, pks), start=1):
        logger.info(f"{Job.__name__}: processing chunk {i}/{chunk_count}")
        if dry_run:
            LIMIT = 10
            logger.info(
                f"{Job.__name__}: dry-run - would delete jobs with PKs "
                f"(limited to {LIMIT} {list(chunk)[:LIMIT]}`"
            )
        else:
            Job.objects.filter(pk__in=chunk).delete()


def _load_model_from_fully_qualified_name(name: str) -> type[AbstractJob]:
    app_label, model_name = name.split(".")
    return apps.get_model(app_label, model_name)
