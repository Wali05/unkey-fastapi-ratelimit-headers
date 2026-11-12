import json

import httpx
import pytest
from fastapi.testclient import TestClient
from unkey.py import Unkey, errors
from unkey.py.errors.unkeyerror import UnkeyError

from app import create_app
from baseline import create_baseline
from fixtures import ROOT, USER_KEY, body, upstream_error

HEADERS = {'Authorization': f'Bearer {USER_KEY}'}


def test_documented_sdk_base_error_is_public():
    assert errors.UnkeyError is UnkeyError
    assert issubclass(errors.InternalServerErrorResponse, UnkeyError)


def test_archived_cookbook_timeout_control_returns_503():
    def handler(request):
        raise httpx.ReadTimeout('synthetic timeout', request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sdk = Unkey(root_key=ROOT, client=client, retry_config=None)
        with TestClient(create_baseline(sdk), raise_server_exceptions=False) as caller:
            response = caller.get('/items', headers=HEADERS)
            assert response.status_code == 503


def test_archived_cookbook_typed_error_control_returns_503():
    with httpx.Client(transport=httpx.MockTransport(lambda r: upstream_error())) as client:
        sdk = Unkey(root_key=ROOT, client=client, retry_config=None)
        with TestClient(create_baseline(sdk), raise_server_exceptions=False) as caller:
            assert caller.get('/items', headers=HEADERS).status_code == 503


def test_archived_cookbook_429_loses_rate_headers():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body('RATE_LIMITED')))) as client:
        sdk = Unkey(root_key=ROOT, client=client, retry_config=None)
        with TestClient(create_baseline(sdk)) as caller:
            response = caller.get('/items', headers=HEADERS)
            assert response.status_code == 429
            assert 'x-ratelimit-remaining' not in response.headers


def call(handler, *, headers=HEADERS, path='/items'):
    calls = []
    def record(request):
        calls.append(request)
        return handler(request)
    with TestClient(create_app(root_key=ROOT, transport=httpx.MockTransport(record))) as client:
        response = client.get(path, headers=headers)
    return response, calls


def test_valid_key_headers_and_exact_request():
    response, calls = call(lambda r: httpx.Response(200, json=body()))
    assert response.status_code == 200
    assert response.json()['credits_left'] == 8
    assert response.headers['x-ratelimit-remaining'] == '9'
    assert response.headers['x-ratelimit-reset'] == '1800000060'
    assert len(calls) == 1
    assert str(calls[0].url) == 'https://api.unkey.com/v2/keys.verifyKey'
    assert calls[0].headers['authorization'] == f'Bearer {ROOT}'
    assert json.loads(calls[0].content)['key'] == USER_KEY


@pytest.mark.parametrize('code,status', [
    ('NOT_FOUND', 401), ('DISABLED', 401), ('EXPIRED', 401),
    ('FORBIDDEN', 403), ('INSUFFICIENT_PERMISSIONS', 403),
    ('USAGE_EXCEEDED', 402), ('RATE_LIMITED', 429),
])
def test_rejection_codes_keep_headers(code, status):
    response, calls = call(lambda r: httpx.Response(200, json=body(code)))
    assert response.status_code == status
    assert response.headers['x-ratelimit-limit'] == '10'
    if code == 'RATE_LIMITED':
        assert response.headers['x-ratelimit-remaining'] == '0'
    assert len(calls) == 1
    if status == 401:
        assert response.headers['www-authenticate'] == 'Bearer'


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Basic fixture'}, {'Authorization': 'Bearer'}])
def test_missing_or_wrong_auth_never_calls_unkey(headers):
    response, calls = call(lambda r: httpx.Response(200, json=body()), headers=headers)
    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer'
    assert calls == []


@pytest.mark.parametrize('error', [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_failure_becomes_503_without_retry(error):
    def handler(request):
        raise error('synthetic private transport detail', request=request)
    response, calls = call(handler)
    assert response.status_code == 503
    assert response.json() == {'detail': 'authentication unavailable'}
    assert len(calls) == 1


@pytest.mark.parametrize('status', [401, 403, 429, 500, 503])
def test_upstream_errors_are_not_customer_denials(status):
    response, calls = call(lambda r: upstream_error(status))
    assert response.status_code == 503
    assert 'private' not in response.text
    assert len(calls) == 1


@pytest.mark.parametrize('payload', [{}, {'meta': {'requestId': 'req_fixture'}, 'data': {}}])
def test_malformed_upstream_fails_closed(payload):
    response, calls = call(lambda r: httpx.Response(200, json=payload))
    assert response.status_code == 503
    assert len(calls) == 1


def test_non_json_fails_closed():
    response, calls = call(lambda r: httpx.Response(200, text='not JSON'))
    assert response.status_code == 503
    assert len(calls) == 1


def test_permission_forwarded_and_optional_ratelimits():
    response, calls = call(lambda r: httpx.Response(200, json=body(rates=False)), path='/reports')
    assert response.status_code == 200
    assert json.loads(calls[0].content)['permissions'] == 'reports.read'
    assert 'x-ratelimit-remaining' not in response.headers


def test_unknown_future_denial_is_not_allowed():
    response, _ = call(lambda r: httpx.Response(200, json=body('NEW_DENIAL_CODE')))
    assert response.status_code == 401


def test_minimal_documentation_patch_also_keeps_429_headers():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body('RATE_LIMITED')))) as client:
        sdk = Unkey(root_key=ROOT, client=client, retry_config=None)
        with TestClient(create_baseline(sdk, 'cookbook-headers.fixed.md')) as caller:
            response = caller.get('/items', headers=HEADERS)
            assert response.status_code == 429
            assert response.headers['x-ratelimit-limit'] == '10'
            assert response.headers['x-ratelimit-remaining'] == '0'
            assert response.headers['x-ratelimit-reset'] == '1800000060'
