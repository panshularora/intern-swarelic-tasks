"""SCAI REST client."""
import logging
import requests
from .config import SCAIClientConfig
from .auth import TokenManager
from .exceptions import SCAIAPIError, SCAIAuthError, SCAINotFoundError, SCAIValidationError

logger = logging.getLogger(__name__)


def _message_from_body(body, fallback: str) -> str:
    if isinstance(body, dict):
        if 'detail' in body:
            return str(body['detail'])
        if 'error' in body:
            return str(body['error'])
    if isinstance(body, str) and body:
        return body
    return fallback


class SCAIClient:
    """Python client for the Swarelic SCAI REST API."""

    def __init__(self, config: SCAIClientConfig):
        self._config = config
        self._token_manager = TokenManager(
            base_url=config.base_url,
            username=config.username,
            password=config.password,
            timeout=config.timeout,
        )
        self._session = requests.Session()
        self._session.verify = config.verify_ssl

    def _parse_body(self, resp: requests.Response):
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return {'detail': resp.text}

    def _request(self, method: str, path: str, _retried: bool = False, **kwargs) -> dict | None:
        url = f"{self._config.base_url.rstrip('/')}{path}"
        timeout = kwargs.pop('timeout', self._config.timeout)
        headers = dict(kwargs.pop('headers', None) or {})
        headers['Authorization'] = f"Bearer {self._token_manager.get_access_token()}"

        resp = self._session.request(method, url, headers=headers, timeout=timeout, **kwargs)

        if resp.status_code == 401 and not _retried:
            logger.info("Got 401, refreshing token and retrying once")
            self._token_manager._refresh()
            return self._request(method, path, _retried=True, **kwargs)

        if resp.status_code == 204:
            return None

        body = self._parse_body(resp)

        if resp.status_code == 404:
            raise SCAINotFoundError(_message_from_body(body, 'Not found'), 404, body)
        if resp.status_code == 400:
            errors = body if isinstance(body, dict) else {'detail': body}
            raise SCAIValidationError(_message_from_body(body, 'Validation error'), errors)
        if resp.status_code in (401, 403):
            raise SCAIAuthError(
                _message_from_body(body, 'Authentication failed'),
                resp.status_code,
                body,
            )
        if resp.status_code >= 400:
            raise SCAIAPIError(
                _message_from_body(body, 'API error'),
                resp.status_code,
                body,
            )
        return body

    def list_call_logs(self, status: str = None, page: int = 1,
                       page_size: int = 20, search: str = None) -> dict:
        params = {'page': page, 'page_size': page_size}
        if status:
            params['status'] = status
        if search:
            params['search'] = search
        return self._request('GET', '/api/v1/call-logs/', params=params)

    def get_call_log(self, call_id: int) -> dict:
        return self._request('GET', f'/api/v1/call-logs/{call_id}/')

    def create_call_log(self, agent_name: str, caller_number: str,
                        duration_secs: int, status: str, notes: str = '') -> dict:
        return self._request('POST', '/api/v1/call-logs/', json={
            'agent_name': agent_name,
            'caller_number': caller_number,
            'duration_secs': duration_secs,
            'status': status,
            'notes': notes,
        })

    def update_call_log(self, call_id: int, **fields) -> dict:
        return self._request('PATCH', f'/api/v1/call-logs/{call_id}/', json=fields)

    def delete_call_log(self, call_id: int) -> None:
        return self._request('DELETE', f'/api/v1/call-logs/{call_id}/')
