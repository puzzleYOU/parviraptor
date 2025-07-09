from parviraptor.test import QueueTestCase

from .models import Counter, DummyJob, DummyProductJob, IncrementCounterJob


class ParallelityTests(QueueTestCase):
    """Schließt Nebenläufigkeitsprobleme bei parallelen Job-Queues aus."""

    def test_status_transition_from_new_to_processing_is_atomic(self):
        COUNTER_VALUE = 500
        jobs = [
            IncrementCounterJob(counter_id="foo") for _ in range(COUNTER_VALUE)
        ]

        # Ohne weitere Sperrmechanismen auf der Datenbank wird es dazu
        # kommen, dass voneinander unabhängige Jobs doppelt abgearbeitet
        # werden können. Wir arbeiten die Queue parallel ab und stellen sicher,
        # dass der Counter auf exakt n erhöht wurde.
        # Wäre er höher, so bedeutet das, dass Jobs doppelt abgearbeitet wurden.
        Counter.objects.create(counter_id="foo", value=0)
        self.process_queue(IncrementCounterJob, jobs, 8)
        self.assertEqual(
            COUNTER_VALUE, Counter.objects.get(counter_id="foo").value
        )

    def test_processes_strict_fifo_queue_in_right_order(self):
        jobs = [DummyJob(a=1, b=3) for _ in range(100)]
        self.process_queue(DummyJob, jobs, 8)

        ordered_ids = self.get_ordered_ids(DummyJob.objects.all(), "pk")
        ids_in_order_of_processing = self.get_ordered_ids(
            DummyJob.objects.all(), "modification_date"
        )
        self.assertEqual(ordered_ids, ids_in_order_of_processing)

    def test_processes_jobs_with_field_based_dependencies_in_right_order(self):
        shops = ["shop-a", "shop-b", "shop-c", "shop-d"]
        products = ["prod-a", "prod-b", "prod-c", "prod-d"]

        jobs = [
            DummyProductJob(
                shop_name=shop_name,
                product_name=product_name,
                action=action,
            )
            for shop_name in shops
            for product_name in products
            for action in range(1, 11)
        ]
        self.process_queue(DummyProductJob, jobs, 8)

        for shop_name in shops:
            for product_name in products:
                jobs = DummyProductJob.objects.filter(
                    shop_name=shop_name, product_name=product_name
                )
                ordered_ids = self.get_ordered_ids(jobs, "pk")
                ids_in_order_of_processing = self.get_ordered_ids(
                    jobs, "modification_date"
                )
                self.assertEqual(ordered_ids, ids_in_order_of_processing)
