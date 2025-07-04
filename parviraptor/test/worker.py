from unittest.mock import Mock

from ..worker import QueueWorker


class InfinityLoopFreeQueueWorker(QueueWorker):
    """
    A non-blocking `QueueWorker` implementation, primarily for automated tests.

    `QueueWorker.run()` by default blocks until there are new processable jobs
    or an exit signal has been caught. This implementation terminates after
    all currently processable jobs have been completed.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._should_stop = False

    @property
    def _caught_exit_signal(self):
        return Mock(is_set=lambda: self._should_stop)

    def run(self, *args, **kwargs):
        super().run(*args, **kwargs)

    def _sleep(self, _):
        self._should_stop = True

    def _setup_signal_handling(self):
        pass
