from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone

from parviraptor.exceptions import TemporaryJobFailure

MAX_TIMEFRAME_FOR_JOB_PROCESSING_IN_MIN = 30
MAX_TIMEFRAME_FOR_UNPROCESSED_JOBS_IN_MIN = 16 * 60


class AbstractJob(models.Model):
    """Basisklasse für eine Job-Queue.

    Apps, die parviraptor verwenden, können konkrete Job-Klassen von dieser
    Basisklasse ableiten. Auf diesem abgeleiteten Job können für diesen Job
    spezifische, weitere Model-Felder definiert werden.

    Diese Basisklasse ist Teil der Public API.
    """

    class Status(models.TextChoices):
        NEW = "NEW"
        PROCESSING = "PROCESSING"
        PROCESSED = "PROCESSED"
        SQUASHED = "SQUASHED"
        FAILED = "FAILED"
        IGNORED = "IGNORED"
        DEFERRED = "DEFERRED"

    creation_date = models.DateTimeField(
        auto_now_add=True,
    )
    modification_date = models.DateTimeField(
        auto_now=True,
    )
    status = models.CharField(
        choices=Status.choices,
        db_index=True,
        default=Status.NEW,
        max_length=32,
    )
    error_count = models.IntegerField(
        default=0,
    )
    error_message = models.TextField(
        blank=True,
        null=True,
    )

    def process(self):
        """Bearbeitet den Job.

        Der Caller stellt sicher, dass `self` der einzige (gleichartige) Job
        mit dem Status PROCESSING ist. Das Status-Handling erfolgt außerhalb
        und ist *nicht* Bestandteil dieser Methode.

        Bei temporären Fehlern, d.h. Fehlern die möglicherweise bei einem
        erneuten Versuch nicht mehr auftreten, *muss* ein `TemporaryJobFailure`
        geworfen werden. Alle anderen Exceptions werden als Fehler behandelt,
        die die Queue-Verarbeitung zum Stillstand bringen. Gleiches gilt, wenn
        ein `TemporaryJobFailure` zu oft auftritt (siehe `worker.py`).

        Sollten Änderungen am Job selbst gemacht werden, muss `self.save()`
        nicht explizit aufgerufen werden. Der Caller macht das ohnehin beim
        Setzen des Status. Änderungen werden auch gespeichert, wenn Exceptions
        geworfen werden! Ist das nicht gewünscht, können z.B. Transaktionen
        verwendet werden.
        """
        raise NotImplementedError()

    def is_processable(self):
        return True

    def get_dependencies_queryset(self):
        """Abhängigkeiten dieses Jobs.

        Die Standardimplementierung behandelt alle älteren Jobs als den
        aktuellen als Abhängigkeit, d.h. das sobald ein Job fehlschlägt, auch
        alle chronologisch folgenden Jobs fehlschlagen.
        """
        return type(self).objects.filter(id__lt=self.id)

    @classmethod
    def count_failed_jobs(cls) -> int:
        return cls.objects.filter(status=cls.Status.FAILED).count()

    @classmethod
    def count_long_processing_jobs(cls) -> int:
        dt = datetime.now(tz=timezone.utc) - timedelta(
            minutes=MAX_TIMEFRAME_FOR_JOB_PROCESSING_IN_MIN
        )

        return cls.objects.filter(
            status=cls.Status.PROCESSING,
            modification_date__lt=dt,
        ).count()

    @classmethod
    def count_long_unprocessed_jobs(cls) -> int:
        dt = datetime.now(tz=timezone.utc) - timedelta(
            minutes=MAX_TIMEFRAME_FOR_UNPROCESSED_JOBS_IN_MIN
        )

        return cls.objects.filter(
            status=cls.Status.NEW,
            creation_date__lt=dt,
        ).count()

    def raise_temporary_failure(self, message: str):
        raise TemporaryJobFailure(message, self.error_count)

    class Meta:
        abstract = True
