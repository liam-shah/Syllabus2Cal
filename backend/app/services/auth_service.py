"""Accounts and login sessions: who is signed in, and signing them in and out.

Knows nothing about HTTP or cookies - it hands out session tokens and looks them up again.
Where a token is kept (a cookie) is the router's business.
"""

import hashlib
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.google_sign_in import GoogleSignIn
from app.models import LoginSession, User, utc_now


def hash_token(token: str) -> str:
    # A fast hash is enough here: the token is 256 random bits, so there's nothing to guess.
    # Slow hashes like bcrypt exist for passwords, which are short and guessable.
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db: Session):
        self._db = db

    def sign_in(self, google: GoogleSignIn) -> tuple[User, str]:
        """Find or create the user, save any new calendar access, and start a session.

        Returns the user and the new session's token - the only time the token exists
        unhashed on the server.
        """
        user = self._find_or_create_user(google)
        # A sign-in without lasting calendar access (e.g. Google skipped the consent screen)
        # must not wipe out access saved on an earlier sign-in.
        if google.calendar_credentials_json is not None:
            user.google_credentials_json = google.calendar_credentials_json

        token = secrets.token_urlsafe(32)
        self._db.add(LoginSession.start(user, hash_token(token)))
        self._delete_expired_sessions(user)
        self._db.commit()
        return user, token

    def user_for_token(self, token: str) -> User | None:
        """The signed-in user for a session token, or None if it's unknown or expired."""
        session = self._db.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(token)))
        if session is None:
            return None
        if session.has_expired():
            self._db.delete(session)
            self._db.commit()
            return None
        return session.user

    def sign_out(self, token: str) -> None:
        """End this one session. Safe to call with a token that's already gone."""
        self._db.execute(delete(LoginSession).where(LoginSession.token_hash == hash_token(token)))
        self._db.commit()

    def _find_or_create_user(self, google: GoogleSignIn) -> User:
        user = self._db.scalar(select(User).where(User.google_subject == google.subject))
        if user is None:
            user = User(google_subject=google.subject)
            self._db.add(user)
        user.email = google.email  # keep up to date: people can change their address
        return user

    def _delete_expired_sessions(self, user: User) -> None:
        # Housekeeping: old sessions are useless, so tidy them up whenever the user signs in.
        self._db.execute(
            delete(LoginSession).where(LoginSession.user_id == user.id, LoginSession.expires_at <= utc_now())
        )
