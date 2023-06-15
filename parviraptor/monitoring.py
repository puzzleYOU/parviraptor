from dataclasses import dataclass
from typing import Iterable, List

from parviraptor.models import AbstractJob


@dataclass(frozen=True)
class QueueMonitoringResult:
    queue_name: str
    failed_jobs_count: int
    long_processing_jobs_count: int


def monitor_queue_entries(
    job_classes: Iterable[type],
) -> List[QueueMonitoringResult]:
    """
    Nimmt eine Sammlung von Job-Klassen entgegen und liefert eine Liste von
    `QueueMonitoringResult`s zurück.

    Ein `QueueMonitoringResult` für die übergebene Job-Klasse taucht nur
    dann im Rückgabewert auf, wenn ein Job fehlgeschlagen oder potentiell
    hängengeblieben ist.

    - Wird bspw. `[DummyJob]` übergeben und es ist kein Job auf `FAILED` oder
      zu lange auf `PROCESSING`, wird `[]` zurückgegeben.

    - Wird bspw. `[DummyJob]` übergeben und es ist 1 Job auf `FAILED` und
      keiner zu lange auf `PROCESSING`, befindet sich in der Rückgabeliste
      ein Element mit `queue_name = "DummyJob"`, `failed_jobs_count = 1`
      und `long_processing_jobs_count = 0`.

    - Wird bspw. `[DummyJob]` übergeben und es ist kein Job auf `FAILED` und
      1 Job zu lange auf `PROCESSING`, befindet sich in der Rückgabeliste
      ein Element mit `queue_name = "DummyJob"`, `failed_jobs_count = 0`
      und `long_processing_jobs_count = 1`.
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

        if failed_jobs_count or long_processing_jobs_count:
            result = QueueMonitoringResult(
                queue_name=job_class.__name__,
                failed_jobs_count=failed_jobs_count,
                long_processing_jobs_count=long_processing_jobs_count,
            )
            results.append(result)
    return results
