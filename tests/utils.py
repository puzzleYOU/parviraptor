import logging
from contextlib import contextmanager


@contextmanager
def disable_logging():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)
