"""AuthService: finding or creating accounts, and starting, checking and ending sessions."""

from datetime import timedelta

from sqlalchemy import select

from app.integrations.google_sign_in import GoogleSignIn
from app.models import LoginSession, User, utc_now
from app.services.auth_service import AuthService, hash_token


def google(subject="google-123", email="a@example.com", calendar: str | None = '{"token": "cal"}') -> GoogleSignIn:
    return GoogleSignIn(subject=subject, email=email, calendar_credentials_json=calendar)


def test_first_sign_in_creates_the_account(db):
    user, _ = AuthService(db).sign_in(google())

    assert db.scalars(select(User)).one() == user
    assert (user.google_subject, user.email, user.google_credentials_json) == ("google-123", "a@example.com", '{"token": "cal"}')


def test_signing_in_again_finds_the_same_account_by_google_id_not_email(db):
    first, _ = AuthService(db).sign_in(google(email="old@example.com"))
    again, _ = AuthService(db).sign_in(google(email="new@example.com"))

    assert again.id == first.id
    assert again.email == "new@example.com"  # kept up to date
    assert len(db.scalars(select(User)).all()) == 1


def test_different_google_accounts_get_different_users(db):
    a, _ = AuthService(db).sign_in(google(subject="google-a"))
    b, _ = AuthService(db).sign_in(google(subject="google-b"))
    assert a.id != b.id


def test_a_sign_in_without_calendar_access_keeps_the_access_saved_earlier(db):
    # A normal sign-in skips Google's consent screen, so it brings no refresh token.
    AuthService(db).sign_in(google(calendar='{"token": "first"}'))
    user, _ = AuthService(db).sign_in(google(calendar=None))
    assert user.google_credentials_json == '{"token": "first"}'


def test_the_token_finds_its_user(db):
    user, token = AuthService(db).sign_in(google())
    assert AuthService(db).user_for_token(token) == user


def test_only_a_hash_of_the_token_is_stored(db):
    _, token = AuthService(db).sign_in(google())

    stored = db.scalars(select(LoginSession)).one()
    assert stored.token_hash == hash_token(token)
    assert token not in stored.token_hash


def test_an_unknown_token_finds_no_one(db):
    AuthService(db).sign_in(google())
    assert AuthService(db).user_for_token("made-up") is None


def test_each_sign_in_gets_its_own_session(db):
    # e.g. a laptop and a phone: signing in on one doesn't sign the other out.
    _, laptop = AuthService(db).sign_in(google())
    _, phone = AuthService(db).sign_in(google())

    assert laptop != phone
    assert AuthService(db).user_for_token(laptop) is not None
    assert AuthService(db).user_for_token(phone) is not None


def test_an_expired_session_finds_no_one_and_is_deleted(db):
    _, token = AuthService(db).sign_in(google())
    session = db.scalars(select(LoginSession)).one()
    session.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()

    assert AuthService(db).user_for_token(token) is None
    assert db.scalars(select(LoginSession)).all() == []


def test_sessions_last_thirty_days(db):
    AuthService(db).sign_in(google())
    session = db.scalars(select(LoginSession)).one()
    assert session.expires_at - session.created_at == timedelta(days=30)


def test_signing_out_ends_only_that_session(db):
    _, laptop = AuthService(db).sign_in(google())
    _, phone = AuthService(db).sign_in(google())

    AuthService(db).sign_out(laptop)

    assert AuthService(db).user_for_token(laptop) is None
    assert AuthService(db).user_for_token(phone) is not None


def test_signing_out_twice_is_harmless(db):
    _, token = AuthService(db).sign_in(google())
    AuthService(db).sign_out(token)
    AuthService(db).sign_out(token)  # no error


def test_signing_in_tidies_away_the_users_expired_sessions(db):
    AuthService(db).sign_in(google())
    db.scalars(select(LoginSession)).one().expires_at = utc_now() - timedelta(days=1)
    db.commit()

    AuthService(db).sign_in(google())

    assert len(db.scalars(select(LoginSession)).all()) == 1  # just the new one
