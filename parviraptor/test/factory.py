from ..utils import enumerate_job_models
from .case import QueueTestCase
from .utils import get_ordered_ids


def make_test_case_for_all_queues(**static_fields) -> type[QueueTestCase]:
    """
    Erzeugt einen Test-Case für alle konkreten Job-Models, die in der
    aktuellen Django-Umgebung existieren.

    Von dieser Klasse kann geerbt werden, um z. B. `setUp()` zu überschreiben,
    was ratsam ist, damit man Dummy-Jobs anlegen kann, die dann verarbeitet
    werden.

    Der Test deckt parallele und sequentielle Verarbeitung der Jobs ab.

    Parameter:
    - `static_fields`: Keyword-Parameter, die als statische Attribute
      auf die Testklasse geschrieben werden. Beispiel für solche Parameter:
      `maxDiff=None`, `fixtures=["some-fixture.json"]`.
    """
    model_classes = enumerate_job_models()

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
                ordered_ids = get_ordered_ids(jobs, "pk")
                ids_in_order_of_processing = get_ordered_ids(
                    jobs, "modification_date"
                )
                self.assertEqual(ordered_ids, ids_in_order_of_processing)

    for field, value in static_fields.items():
        setattr(_TestCase, field, value)
    return _TestCase
