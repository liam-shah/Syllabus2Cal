"""The app's exception hierarchy.

Errors are grouped by *kind* of failure, not by which library failed. main.py maps
each kind to an HTTP status code, so new errors only need the right parent class.

    AppError
    ├── NotFoundError          (404)
    ├── InvalidInputError      (400)   e.g. PDFExtractionError
    └── ExternalServiceError   (502)   e.g. LLMExtractionError, GoogleCalendarError
"""


class AppError(Exception):
    """Base class for failures the app expects and knows how to report."""


class NotFoundError(AppError):
    """The requested item doesn't exist, or belongs to another user."""


class InvalidInputError(AppError):
    """The user sent something the app can't use (e.g. a file that isn't a PDF)."""


class ExternalServiceError(AppError):
    """An outside service (Claude, Google) failed or returned something unusable."""
