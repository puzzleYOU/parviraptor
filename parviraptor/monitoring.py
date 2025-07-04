from dataclasses import dataclass
from typing import Iterable, List

from parviraptor.models.abstract import AbstractJob


@dataclass(frozen=True)
class QueueMonitoringResult:
    queue_name: str
    failed_jobs_count: int
    long_processing_jobs_count: int
    long_unprocessed_jobs_count: int


def monitor_queue_entries(
    job_classes: Iterable[type],
) -> List[QueueMonitoringResult]:
    """
    Returns `QueueMonitoringResult` per passed job class.

    A `QueueMonitoringResult` is returned per job class if at least one of the
    following conditions is met:
    - jobs failed (failed_jobs_count > 0)
    - backlog is potentially too large (long_unprocessed_jobs_count > 0)
    - jobs potentially crashed (long_processing_jobs_count > 1)
    """

    mistyped_classes = list(
        filter(
            lambda job_class: not issubclass(job_class, AbstractJob),
            job_classes,
        )
    )

    if mistyped_classes:
        raise TypeError(mistyped_classes)

    results = []

    for job_class in job_classes:
        failed_jobs_count = job_class.count_failed_jobs()
        long_processing_jobs_count = job_class.count_long_processing_jobs()
        long_unprocessed_jobs_count = job_class.count_long_unprocessed_jobs()

        if (
            failed_jobs_count
            or long_processing_jobs_count
            or long_unprocessed_jobs_count
        ):
            result = QueueMonitoringResult(
                queue_name=job_class.__name__,
                failed_jobs_count=failed_jobs_count,
                long_processing_jobs_count=long_processing_jobs_count,
                long_unprocessed_jobs_count=long_unprocessed_jobs_count,
            )
            results.append(result)
    return results
