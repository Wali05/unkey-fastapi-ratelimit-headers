"""Loopback-only demo entry point: all Unkey calls are intercepted locally."""
import httpx
from app import create_app
from fixtures import ROOT, body


def handler(request):
    # Synthetic keys are intentionally human-readable; no real account required.
    import json
    key = json.loads(request.content)['key']
    code = {'demo-valid': 'VALID', 'demo-limited': 'RATE_LIMITED'}.get(key, 'NOT_FOUND')
    return httpx.Response(200, json=body(code))


app = create_app(root_key=ROOT, transport=httpx.MockTransport(handler))
