from itertools import chain, islice
from typing import List

from django.apps import apps


def enumerate_job_models() -> List[type]:
    """
    Enumerates all non-abstract parviraptor job models within current
    Django environment.
    """
    # avoid circular imports
    from parviraptor.models.abstract import AbstractJob

    all_apps = apps.get_app_configs()
    relevant_models = list(chain(*(app.get_models() for app in all_apps)))

    def is_abstract(model_class):
        if not hasattr(model_class, "Meta"):
            # If there is no meta class, `abstract = True` can not have
            # been explicitly set so the model is logically non-abstract
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


def iter_chunks(size, iterable):
    """Divides `iterable` into tuples of `size`. The last chunk may be shorter.

    >>> list(iter_chunks(3, range(14)))
    [(0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11), (12, 13)]

    source: https://stackoverflow.com/a/22045226
    """
    it = iter(iterable)
    return iter(lambda: tuple(islice(it, size)), ())
