from django.urls import path

from .views import OpenQueueEntriesView, queue_monitoring

urlpatterns = [
    path("queue-monitoring/", queue_monitoring, name="queue-monitoring"),
    path(
        "open-queue-entries/",
        OpenQueueEntriesView.as_view(),
        name="open-queue-entries",
    ),
]
