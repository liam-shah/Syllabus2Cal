"""App configuration, loaded from environment variables and backend/.env.

Each setting is read from an environment variable with the same name in capitals
(e.g. frontend_url <- FRONTEND_URL). The defaults are for local development; a
deployed copy of the app overrides them in its own environment.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    anthropic_api_key: str
    # Signs the session cookie, so a browser can't forge or edit it. Long and random; keep it secret.
    session_secret_key: str
    google_client_secret_path: Path = BACKEND_DIR / "client_secret.json"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'app.db').as_posix()}"

    # Where each half of the app is running. Used for CORS and the Google sign-in redirects.
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    @property
    def cookies_need_https(self) -> bool:
        """Mark cookies Secure (sent over HTTPS only) whenever the app is served over HTTPS."""
        return self.backend_url.startswith("https://")


settings = Settings()
