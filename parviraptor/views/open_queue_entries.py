from django.shortcuts import render

from ..models.abstract import JobStatus
from ..utils import enumerate_job_models


def open_queue_entries(request):
    open_queue_entries = {
        job_class.__name__: job_class.objects.filter(
            status__in=[JobStatus.NEW, JobStatus.PROCESSING],
        ).count()
        for job_class in enumerate_job_models()
    }

    context = {"open_queue_entries": open_queue_entries}
    return render(request, "parviraptor/open_queue_entries.html", context)
