from django.shortcuts import render
from django.views.generic import View

from ..models.abstract import JobStatus
from ..utils import enumerate_job_models


class OpenQueueEntriesView(View):
    def get(self, request):
        context = self.get_context()
        return render(request, "parviraptor/open_queue_entries.html", context)

    def get_context(self) -> dict:
        open_queue_entries = {
            job_class.__name__: job_class.objects.filter(
                status__in=[JobStatus.NEW, JobStatus.PROCESSING],
            ).count()
            for job_class in enumerate_job_models()
        }

        return {"open_queue_entries": open_queue_entries}
