"""Offline before/after comparison through real FastAPI + official Unkey SDK."""
import httpx
from fastapi.testclient import TestClient
from unkey.py import Unkey
from app import create_app
from baseline import create_baseline
from fixtures import ROOT, USER_KEY, body


def show(label, response):
    headers = {k: v for k, v in response.headers.items() if k.startswith('x-ratelimit-')}
    print(f'{label}: status={response.status_code}; rate-limit headers={headers}')


def main():
    def handler(request):
        assert str(request.url) == 'https://api.unkey.com/v2/keys.verifyKey'
        return httpx.Response(200, json=body('RATE_LIMITED'))
    headers = {'Authorization': f'Bearer {USER_KEY}'}
    for label, source in [('Current docs', 'evidence/fastapi-auth-source.md'),
                          ('Minimal patch', 'cookbook-headers.fixed.md')]:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            sdk = Unkey(root_key=ROOT, client=client, retry_config=None)
            with TestClient(create_baseline(sdk, source)) as caller:
                response = caller.get('/items', headers=headers)
                show(label, response)
    with TestClient(create_app(root_key=ROOT, transport=httpx.MockTransport(handler))) as caller:
        show('Async example', caller.get('/items', headers=headers))


if __name__ == '__main__':
    main()
