"""Safe, structured failures shared by resume intake services."""


class ResumeProcessingError(Exception):
    """A file failure, never evidence that a candidate lacks a skill."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
