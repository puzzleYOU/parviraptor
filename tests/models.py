import signal
from random import randint
from time import sleep

from django.db import models, transaction

from parviraptor.exceptions import DeferJob, IgnoreJob, InvalidJobError
from parviraptor.models import AbstractJobFactory

MAX_ERROR_COUNT = 5


class DummyJob(AbstractJobFactory.make_base_class([])):
    """Beispiel-Job zu Demonstrations- und Testzwecken."""

    a = models.IntegerField()
    b = models.IntegerField()
    result = models.IntegerField(
        null=True,
    )

    def process(self):
        sleep_randomly()

        if self.a == 0 and self.b == 100000:
            self.raise_temporary_failure("always fail temporarily")

        self.result = self.a + self.b

        # Normalerweise kommen die Signals von außerhalb. Zum Testen ist es
        # aber leichter, wenn wir sie deterministisch selbst senden können, und
        # zwar während der Verarbeitung eines Jobs (d.h. "in" `Job.process()`,
        # also hier:
        if self.result < 0:
            signal.raise_signal(signal.SIGTERM)

        # Willkürliches Beispiel für TemporaryJobFailure, i.d.R. sollte
        # `process` nur auf die hier definierten Felder zugreifen müssen, und
        # den `error_count` komplett ignorieren.
        if self.a == 0 and self.error_count < MAX_ERROR_COUNT:
            self.raise_temporary_failure("adding to 0 failed")
        elif self.b == 0:
            raise ValueError("b cannot be 0")
        elif self.result == 100:
            raise InvalidJobError(f"Ignoring result {self.result}")
        elif self.result == 200:
            raise IgnoreJob(f"Ignoring result {self.result}")
        elif self.result == 300:
            raise DeferJob(f"Deferring result {self.result}")


class Counter(models.Model):
    counter_id = models.CharField(max_length=16, primary_key=True)
    value = models.IntegerField()


class IncrementCounterJob(AbstractJobFactory.make_base_class(None)):
    counter_id = models.CharField(max_length=16)

    @transaction.atomic
    def process(self):
        state = (
            Counter.objects.select_for_update()
            .filter(counter_id=self.counter_id)
            .first()
        )
        state.value += 1
        state.save()


class DummyProductJob(
    AbstractJobFactory.make_base_class(["shop_name", "product_name"])
):
    shop_name = models.CharField(max_length=16, db_index=True)
    product_name = models.CharField(max_length=16, db_index=True)
    action = models.CharField(max_length=16)

    def process(self):
        sleep_randomly()


def sleep_randomly():
    sleep(0.001 * randint(0, 10))
