from django.urls import path

from .views import open_queue_entries, queue_monitoring

urlpatterns = [
    path("queue-monitoring/", queue_monitoring, name="queue-monitoring"),
    path("open-queue-entries/", open_queue_entries, name="open-queue-entries"),
]
