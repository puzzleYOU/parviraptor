from django.shortcuts import render

from ..monitoring import monitor_queue_entries
from ..utils import enumerate_job_models


def queue_monitoring(request):
    job_classes = enumerate_job_models()
    queue_entries = monitor_queue_entries(job_classes)
    context = {"queue_entries": queue_entries}
    return render(request, "parviraptor/queue_monitoring.html", context)
