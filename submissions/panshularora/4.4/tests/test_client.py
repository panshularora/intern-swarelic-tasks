"""Tests for SCAI client. HTTP is mocked with responses."""
import pytest
import responses as responses_lib

from scai_client import SCAIClient, SCAIClientConfig
from scai_client.exceptions import SCAINotFoundError, SCAIValidationError, SCAIAPIError


BASE_URL = 'http://test.scai.local'
TOKEN_URL = f'{BASE_URL}/api/auth/token/'
REFRESH_URL = f'{BASE_URL}/api/auth/token/refresh/'
CALL_LOGS_URL = f'{BASE_URL}/api/v1/call-logs/'

MOCK_TOKENS = {
    'access': 'mock-access-token-abc123',
    'refresh': 'mock-refresh-token-xyz789',
}

MOCK_CALL_LOG = {
    'id': 1,
    'agent_name': 'Alice',
    'caller_number': '+91-9876543210',
    'duration_secs': 180,
    'status': 'completed',
    'notes': '',
    'duration_display': '3m 0s',
    'timestamp': '2024-01-15T14:30:00Z',
}


@pytest.fixture
def config():
    return SCAIClientConfig(
        base_url=BASE_URL,
        username='testuser',
        password='testpass123',
    )


@pytest.fixture
def client(config):
    return SCAIClient(config)


def register_login_mock():
    responses_lib.add(
        responses_lib.POST, TOKEN_URL,
        json=MOCK_TOKENS, status=200
    )


class TestConfig:

    def test_valid_config_passes(self):
        config = SCAIClientConfig(
            base_url='http://localhost:8000',
            username='alice',
            password='secret',
        )
        assert config.base_url == 'http://localhost:8000'

    def test_invalid_base_url_raises(self):
        with pytest.raises(ValueError, match="http"):
            SCAIClientConfig(base_url='ftp://bad-url', username='a', password='b')

    def test_empty_username_raises(self):
        with pytest.raises(ValueError):
            SCAIClientConfig(base_url='http://localhost', username='', password='pass')

    def test_zero_timeout_raises(self):
        with pytest.raises(ValueError):
            SCAIClientConfig(base_url='http://localhost', username='a', password='b', timeout=0)


class TestAuthentication:

    @responses_lib.activate
    def test_auto_login_on_first_request(self, client):
        register_login_mock()
        responses_lib.add(
            responses_lib.GET, CALL_LOGS_URL,
            json={'count': 0, 'results': []}, status=200
        )
        client.list_call_logs()
        assert len(responses_lib.calls) == 2
        assert responses_lib.calls[0].request.url == TOKEN_URL

    @responses_lib.activate
    def test_token_sent_in_authorization_header(self, client):
        register_login_mock()
        responses_lib.add(
            responses_lib.GET, CALL_LOGS_URL,
            json={'count': 0, 'results': []}, status=200
        )
        client.list_call_logs()
        api_call = responses_lib.calls[1]
        assert 'Authorization' in api_call.request.headers
        assert 'Bearer' in api_call.request.headers['Authorization']


class TestCallLogs:

    @responses_lib.activate
    def test_list_call_logs_returns_dict(self, client):
        register_login_mock()
        mock_response = {'count': 1, 'next': None, 'previous': None, 'results': [MOCK_CALL_LOG]}
        responses_lib.add(responses_lib.GET, CALL_LOGS_URL, json=mock_response, status=200)

        result = client.list_call_logs()
        assert result['count'] == 1
        assert len(result['results']) == 1

    @responses_lib.activate
    def test_get_call_log_not_found_raises(self, client):
        register_login_mock()
        responses_lib.add(
            responses_lib.GET, f'{CALL_LOGS_URL}999/',
            json={'detail': 'Not found.'}, status=404
        )
        with pytest.raises(SCAINotFoundError):
            client.get_call_log(999)

    @responses_lib.activate
    def test_create_call_log_returns_created_object(self, client):
        register_login_mock()
        responses_lib.add(responses_lib.POST, CALL_LOGS_URL, json=MOCK_CALL_LOG, status=201)

        result = client.create_call_log(
            agent_name='Alice',
            caller_number='+91-9876543210',
            duration_secs=180,
            status='completed',
        )
        assert result['id'] == 1
        assert result['agent_name'] == 'Alice'

    @responses_lib.activate
    def test_delete_call_log_returns_none(self, client):
        register_login_mock()
        responses_lib.add(
            responses_lib.DELETE, f'{CALL_LOGS_URL}1/',
            body='', status=204
        )
        result = client.delete_call_log(1)
        assert result is None

    @responses_lib.activate
    def test_list_with_status_filter(self, client):
        register_login_mock()
        responses_lib.add(responses_lib.GET, CALL_LOGS_URL,
                          json={'count': 0, 'results': []}, status=200)
        client.list_call_logs(status='missed')
        api_call = responses_lib.calls[1]
        assert 'status=missed' in api_call.request.url


class TestErrorHandling:

    @responses_lib.activate
    def test_400_raises_validation_error(self, client):
        register_login_mock()
        responses_lib.add(
            responses_lib.POST, CALL_LOGS_URL,
            json={'duration_secs': ['Ensure this value is greater than or equal to 0.']},
            status=400
        )
        with pytest.raises(SCAIValidationError) as exc_info:
            client.create_call_log('Alice', '+91-0000', -1, 'completed')
        assert exc_info.value.status_code == 400

    @responses_lib.activate
    def test_500_raises_api_error(self, client):
        register_login_mock()
        responses_lib.add(
            responses_lib.GET, CALL_LOGS_URL,
            json={'error': 'Internal Server Error'}, status=500
        )
        with pytest.raises(SCAIAPIError) as exc_info:
            client.list_call_logs()
        assert exc_info.value.status_code == 500

    @responses_lib.activate
    def test_401_triggers_token_refresh(self, client):
        register_login_mock()
        responses_lib.add(
            responses_lib.GET, CALL_LOGS_URL,
            json={'detail': 'Token expired'}, status=401
        )
        responses_lib.add(
            responses_lib.POST, REFRESH_URL,
            json={'access': 'new-access', 'refresh': 'new-refresh'}, status=200
        )
        responses_lib.add(
            responses_lib.GET, CALL_LOGS_URL,
            json={'count': 0, 'results': []}, status=200
        )
        result = client.list_call_logs()
        assert result['count'] == 0
