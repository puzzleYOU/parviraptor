from itertools import chain
from typing import Iterable

from django.apps import AppConfig

from parviraptor.models import AbstractJob


def enumerate_job_models(relevant_apps: Iterable[AppConfig]):
    relevant_models = list(chain(*(app.get_models() for app in relevant_apps)))

    def is_abstract(model_class):
        if not hasattr(model_class, "Meta"):
            # Wenn keine Meta-Klasse gesetzt ist, kann auch nicht
            # explizit `abstract = True` gesetzt sein.
            return False
        return not getattr(model_class.Meta, "abstract", False)

    non_abstract_models = list(filter(is_abstract, relevant_models))
    job_models = list(
        filter(
            lambda model_class: issubclass(model_class, AbstractJob),
            non_abstract_models,
        )
    )

    return job_models
