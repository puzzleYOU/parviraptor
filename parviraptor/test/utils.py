from contextlib import contextmanager
from cProfile import Profile
from pstats import SortKey, Stats
from sys import stdout


@contextmanager
def measure_stats():
    pr = Profile()
    pr.enable()
    yield
    pr.disable()
    Stats(pr, stream=stdout).sort_stats(SortKey.CUMULATIVE).print_stats()


def get_ordered_ids(qs, field):
    return [job.pk for job in qs.order_by(field)]
