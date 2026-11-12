"""Synthetic response data following Unkey's documented verifyKey schema."""
import httpx

ROOT = 'fixture-root-not-a-real-key'
USER_KEY = 'fixture-user-not-a-real-key'

def body(code='VALID', *, rates=True):
    data = {'valid': code == 'VALID', 'code': code, 'keyId': 'key_fixture', 'credits': 8}
    if rates:
        data['ratelimits'] = [{
            'id': 'rl_fixture123', 'name': 'api_requests', 'limit': 10,
            'remaining': 0 if code == 'RATE_LIMITED' else 9,
            'duration': 60000, 'reset': 1800000060000,
            'exceeded': code == 'RATE_LIMITED', 'autoApply': True,
        }]
    return {'meta': {'requestId': 'req_fixture'}, 'data': data}


def upstream_error(status=500):
    return httpx.Response(status, json={
        'meta': {'requestId': 'req_fixture'},
        'error': {'title': 'fixture error', 'detail': 'synthetic private error detail',
                  'status': status, 'type': 'https://www.unkey.com/docs/errors/fixture'},
    })
