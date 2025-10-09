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
            "max_age_in_days",
            type=int,
            help=(
                """
                Jobs which are as old or older than the given age in
                days are removed. If there is a not successfully finished
                job within the resulting timeframe, only the jobs until the
                first failed job are removed if there are some.
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

    def handle(self, max_age_in_days: int, **options):
        relevant_job_models: list[type[AbstractJob]] = (
            enumerate_job_models()
            if options["all_queues"]
            else [_load_model_from_fully_qualified_name(options["queue"])]
        )
        for Job in relevant_job_models:
            _delete_old_finished_jobs(Job, max_age_in_days)


def _delete_old_finished_jobs(Job: type[AbstractJob], max_age_in_days: int):
    border = datetime.now(tz=timezone.utc) - timedelta(days=max_age_in_days)
    old_jobs = Job.objects.filter(modification_date__lte=border)
    if maybe_unfinished_job := old_jobs.exclude(
        status__in=("PROCESSED", "DEFERRED", "IGNORED")
    ).first():
        _delete_in_chunks(Job, old_jobs.filter(id__lt=maybe_unfinished_job.pk))
    else:
        _delete_in_chunks(Job, old_jobs)


def _delete_in_chunks(Job: type[AbstractJob], jobs):
    pks = jobs.values_list("pk", flat=True)
    pks_count = pks.count()

    CHUNK_SIZE = 2_000
    full_chunks = pks_count // CHUNK_SIZE
    remainder = 0 if pks_count % CHUNK_SIZE == 0 else 1
    chunk_count = full_chunks + remainder

    for i, chunk in enumerate(iter_chunks(CHUNK_SIZE, pks), start=1):
        logger.info(f"{Job.__name__}: processing chunk {i}/{chunk_count}")
        Job.objects.filter(pk__in=chunk).delete()


def _load_model_from_fully_qualified_name(name: str) -> type[AbstractJob]:
    app_label, model_name = name.split(".")
    return apps.get_model(app_label, model_name)
