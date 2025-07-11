from parviraptor.models.abstract import AbstractJob

from ..utils import enumerate_job_models
from .case import QueueTestCase


def make_test_case_for_all_queues[
    TJob: AbstractJob
](
    job_classes_to_ignore: list[type[TJob]] | None = None,
    **static_fields,
) -> type[QueueTestCase]:
    """
    Infers a test case for all non-abstract parviraptor job models within
    the current Django environment.

    It covers processing jobs both sequentially and in parallel, and ensures
    job instances exist for each concrete job class. Therefore, you should
    derive from the inferred base class and extend `setUp()` to create job
    instances.

    Parameters:
    - `job_classes_to_ignore`: One might experience that it might come to
      race conditions if job queues depend on each other in any manner. It
      might be intentional to exclude such queues or having disjoint testcases
      for such groups of queues.
    - `static_fields`: keyword parameters. they are directly passed as static
      members to the test class. One might want to pass `maxDiff=None` and
      `fixtures=["some-fixture.json"]`, for example.
    """
    model_classes = [
        installed_model
        for installed_model in enumerate_job_models()
        if installed_model not in (job_classes_to_ignore or [])
    ]

    class _TestCase(QueueTestCase):
        queues = [model_class.__name__ for model_class in model_classes]

        def test_can_process_queue_sequentially(self):
            self._process_all_queues(num_workers=1)

        def test_can_process_queue_concurrently(self):
            self._process_all_queues(num_workers=8)

        def _process_all_queues(self, num_workers: int):
            for model_class in model_classes:
                with self.subTest(model_class.__name__):
                    self.assertGreater(model_class.objects.count(), 0)
                    self.process_queue(
                        model_class,
                        model_class.objects.all(),
                        num_workers,
                        create_jobs=False,
                    )
                    self._assert_jobs_are_processed_in_proper_order(model_class)

        def _assert_jobs_are_processed_in_proper_order(self, model_class):
            for f in model_class.get_queryset_filters_for_disjoint_queues():
                jobs = model_class.objects.filter(**f)
                ordered_ids = self.get_ordered_ids(jobs, "pk")
                ids_in_order_of_processing = self.get_ordered_ids(
                    jobs, "modification_date"
                )
                self.assertEqual(ordered_ids, ids_in_order_of_processing)

    for field, value in static_fields.items():
        setattr(_TestCase, field, value)
    return _TestCase
