from unittest.mock import Mock

from ..worker import QueueWorker


class InfinityLoopFreeQueueWorker(QueueWorker):
    """
    Spezialisierung des `QueueWorker`.

    `run()` im `QueueWorker` ist eine Endlosschleife. Sobald keine Jobs mehr
    vorhanden sind, geht der Worker in einen `sleep()`-Zustand über, bis
    wieder Jobs geholt werden.

    Der `InfinityLoopFreeQueueWorker` beendet sich, sobald zum ersten Mal
    in diesen `sleep()`-Zustand übergegangen würde (= keine Jobs mehr offen
    sind). Damit lässt sich der Worker leichter in Unittests testen.
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
