from django.apps import apps
from django.core.management.base import BaseCommand

from parviraptor.worker import QueueWorker


class Command(BaseCommand):
    help = "Call QueueWorker for a specific model"

    def add_arguments(self, parser):
        parser.add_argument(
            "app_label",
            type=str,
        )
        parser.add_argument(
            "model_name",
            type=str,
        )

    def handle(self, app_label, model_name, *args, **options):
        Model = apps.get_model(app_label, model_name)
        worker = QueueWorker(Model)

        self.stdout.write(f"Starting QueueWorker for {model_name} ...")

        worker.run()

        self.stdout.write(f"Stopping QueueWorker for {model_name}")
