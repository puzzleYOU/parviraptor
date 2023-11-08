from unittest import TestCase

from parviraptor.test import make_test_case_for_all_queues

from .models import Counter, DummyJob, DummyProductJob, IncrementCounterJob


class FactoryTestCase(make_test_case_for_all_queues()):
    def setUp(self):
        super().setUp()
        DummyJob.objects.bulk_create(
            [DummyJob(a=1, b=3) for _ in range(0, 100)]
        )
        DummyProductJob.objects.bulk_create(
            [
                DummyProductJob(
                    shop_name=shop_name,
                    product_name=product_name,
                    action=action,
                )
                for shop_name in ["shop-a", "shop-b", "shop-c", "shop-d"]
                for product_name in ["prod-a", "prod-b", "prod-c", "prod-d"]
                for action in ["FOO", "BAR", "BAZ"]
            ]
        )
        Counter.objects.create(counter_id="foo", value=0)
        IncrementCounterJob.objects.bulk_create(
            [IncrementCounterJob(counter_id="foo") for _ in range(0, 100)]
        )


class MakeTestCaseForAllQueuesTests(TestCase):
    def test_covers_all_models_within_current_django_installation(self):
        self.assertEqual(
            ["DummyJob", "IncrementCounterJob", "DummyProductJob"],
            FactoryTestCase.queues,
        )

    def test_appends_static_fields_properly(self):
        WithoutStaticFields = make_test_case_for_all_queues()
        self.assertFalse(hasattr(WithoutStaticFields, "some_arbitrary_field"))

        WithStaticFields = make_test_case_for_all_queues(
            some_arbitrary_field=1337,
        )
        self.assertEqual(1337, WithStaticFields.some_arbitrary_field)
