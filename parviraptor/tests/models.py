import signal

from django.db import models

from parviraptor.exceptions import InvalidJobError
from parviraptor.models.abstract import AbstractJob

MAX_ERROR_COUNT = 5


class DummyJob(AbstractJob):
    """Beispiel-Job zu Demonstrations- und Testzwecken."""

    a = models.IntegerField()
    b = models.IntegerField()
    result = models.IntegerField(
        null=True,
    )

    def process(self):
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
            self._raise_temporary_failure("adding to 0 failed")
        elif self.b == 0:
            raise ValueError("b cannot be 0")
        elif self.result == 100:
            raise InvalidJobError(f"Ignoring result {self.result}")
