class DeferJob(Exception):
    pass


class IgnoreJob(Exception):
    pass


class UnprocessableJob(Exception):
    pass


class InvalidJobError(Exception):
    pass


class TemporaryJobFailure(Exception):
    def __init__(self, message: str, error_count: int):
        self._message = message
        self._error_count = error_count

    def __str__(self):
        return self._message

    @property
    def message(self):
        return self._message

    @property
    def error_count(self):
        return self._error_count
