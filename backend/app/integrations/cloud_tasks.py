"""Cloud Tasks: checking that a request to the worker route really comes from our queue.

The worker route is on the same public Cloud Run service as the rest of the API, so anyone
can call it. Cloud Tasks attaches a Google-signed ID token (OIDC) for the tasks service
account, with this service's URL as its audience; only a token like that is accepted.
"""

from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.errors import NotSignedInError


class TaskTokenError(NotSignedInError):
    """The request isn't from our Cloud Tasks queue (-> 401)."""


def verify_task_token(token: str, audience: str, service_account: str) -> None:
    """Raise TaskTokenError unless `token` is a Google-signed token for `service_account`,
    issued for `audience` (this service's own URL)."""
    try:
        # Checks Google's signature, that the token hasn't expired, and the audience: a token
        # minted for some other service can't be replayed here. Fetches Google's public keys.
        claims = id_token.verify_oauth2_token(token, Request(), audience=audience)
    except ValueError as e:
        # A fixed message: the reason (bad signature, wrong audience...) is no business of the caller's.
        raise TaskTokenError("This request isn't from the extraction queue.") from e

    # Anyone can get a Google-signed token for *their own* account with our URL as audience,
    # so the signature alone proves nothing - it has to be the tasks account's.
    if claims.get("email") != service_account or not claims.get("email_verified"):
        raise TaskTokenError("This request isn't from the extraction queue.")
