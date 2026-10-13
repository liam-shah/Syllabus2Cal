"""What the browser's session cookie holds - the only module that knows its layout.

The cookie is managed by Starlette's SessionMiddleware (set up in main.py): it holds a small
dict, signed with SESSION_SECRET_KEY so the browser can read it but not change or forge it.
It holds one of two things:

  - during sign-in:  the login attempt (state + PKCE code_verifier) until Google sends the
                     user back. Keeping it in *this browser's* cookie means a sign-in can only
                     be finished by the browser that started it.
  - once signed in:  the session token, which AuthService looks up in the database.

The cookie is called "__session" because Firebase Hosting, when it forwards requests to a
backend, removes every cookie except one with that name.
"""

import secrets

from fastapi import Request

COOKIE_NAME = "__session"

_TOKEN = "token"
_LOGIN_ATTEMPT = "login_attempt"


def read_token(request: Request) -> str | None:
    return request.session.get(_TOKEN)


def start_login_attempt(request: Request, state: str, code_verifier: str) -> None:
    # Added alongside any current session: if the user cancels on Google's page, they're
    # still signed in.
    request.session[_LOGIN_ATTEMPT] = {"state": state, "code_verifier": code_verifier}


def finish_login_attempt(request: Request, state: str | None) -> str | None:
    """The code_verifier for this sign-in, or None if this browser didn't start it.

    Removed as it's read, so each sign-in link only works once.
    """
    attempt = request.session.pop(_LOGIN_ATTEMPT, None)
    if attempt is None or state is None or not secrets.compare_digest(attempt["state"], state):
        return None
    return attempt["code_verifier"]


def start_session(request: Request, token: str) -> None:
    # Clear first, so nothing from before signing in carries over into the signed-in session.
    request.session.clear()
    request.session[_TOKEN] = token


def end_session(request: Request) -> None:
    request.session.clear()  # SessionMiddleware then tells the browser to delete the cookie
