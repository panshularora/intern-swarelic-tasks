"""JWT token login / refresh."""
import logging
import requests
from datetime import datetime, timedelta
from .exceptions import SCAIAuthError

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_LIFETIME_SECS = 3600


class TokenManager:
    """Manages JWT access and refresh tokens for the SCAI API."""

    REFRESH_THRESHOLD_SECS = 60

    def __init__(self, base_url: str, username: str, password: str, timeout: int):
        self._base_url = base_url.rstrip('/')
        self._username = username
        self._password = password
        self._timeout = timeout
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: datetime | None = None

    def get_access_token(self) -> str:
        if self._access_token is None:
            self._login()
        elif self.is_expired:
            self._refresh()
        return self._access_token

    def _store_tokens(self, data: dict) -> None:
        access = data.get('access')
        if not access:
            raise SCAIAuthError("Auth response missing access token")
        self._access_token = access
        if data.get('refresh'):
            self._refresh_token = data['refresh']
        lifetime = data.get('expires_in') or data.get('lifetime') or DEFAULT_TOKEN_LIFETIME_SECS
        self._expires_at = datetime.now() + timedelta(seconds=int(lifetime))

    def _login(self) -> None:
        url = f"{self._base_url}/api/auth/token/"
        try:
            resp = requests.post(
                url,
                json={'username': self._username, 'password': self._password},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SCAIAuthError(f"Login request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise SCAIAuthError("Login failed", status_code=resp.status_code)
        try:
            data = resp.json()
        except ValueError as exc:
            raise SCAIAuthError("Login response was not JSON") from exc
        self._store_tokens(data)
        logger.debug("Logged in to SCAI")

    def _refresh(self) -> None:
        if not self._refresh_token:
            logger.info("No refresh token, falling back to login")
            self._login()
            return

        url = f"{self._base_url}/api/auth/token/refresh/"
        try:
            resp = requests.post(
                url,
                json={'refresh': self._refresh_token},
                timeout=self._timeout,
            )
        except requests.RequestException:
            logger.warning("Refresh request failed, falling back to login")
            self._login()
            return

        if resp.status_code >= 400:
            logger.warning("Refresh rejected (%s), falling back to login", resp.status_code)
            self._login()
            return

        try:
            data = resp.json()
        except ValueError:
            self._login()
            return
        self._store_tokens(data)

    def invalidate(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._expires_at = None

    @property
    def is_expired(self) -> bool:
        if self._expires_at is None:
            return True
        remaining = (self._expires_at - datetime.now()).total_seconds()
        return remaining < self.REFRESH_THRESHOLD_SECS
