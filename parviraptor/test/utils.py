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
