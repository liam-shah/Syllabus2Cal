"""The app's exception hierarchy.

Errors are grouped by *kind* of failure, not by which library failed. main.py maps
each kind to an HTTP status code, so new errors only need the right parent class.

    AppError
    ├── NotFoundError          (404)
    ├── InvalidInputError      (400)   e.g. PDFExtractionError
    ├── ConflictError          (409)   e.g. editing an event that's already synced
    └── ExternalServiceError   (502)   e.g. LLMExtractionError, GoogleCalendarError
"""


class AppError(Exception):
    """Base class for failures the app expects and knows how to report."""


class NotSignedInError(AppError):
    """The request needs a signed-in user, and there isn't one (or their session expired)."""


class NotFoundError(AppError):
    """The requested item doesn't exist, or belongs to another user."""


class InvalidInputError(AppError):
    """The user sent something the app can't use (e.g. a file that isn't a PDF)."""


class ConflictError(AppError):
    """The request is valid, but the item's current state doesn't allow it."""


class ExternalServiceError(AppError):
    """An outside service (Claude, Google) failed or returned something unusable."""
