# Keep Unkey rate-limit headers on FastAPI 429s

Unkey's [FastAPI authentication cookbook](https://www.unkey.com/docs/api-management/cookbook/fastapi-auth.md) verifies a key and sets `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` on FastAPI's injected `Response`. When the dependency raises `HTTPException` — a 429, for example — FastAPI builds a separate error response, and those headers are dropped. The cookbook already mentions this and says to pass the headers in the exception if you need them on rejections.

This repo turns that note into a runnable example:

- `cookbook-headers.patch` — the small change the cookbook describes: build a headers dict, pass it to `HTTPException`, and apply it on success.
- `cookbook-headers.fixed.md` — the cookbook snippet with that change applied.
- `baseline.py` — runs the original snippet as a control (SDK construction is injected so it can be tested offline).
- `app.py` — an async FastAPI app using the official [`unkey.py`](https://pypi.org/project/unkey.py/) SDK, with the headers kept on rejection, a lifespan-managed client, route-specific permissions, a timeout, and no automatic retries.
- `reproduce.py` — offline before/after comparison through real FastAPI and the real SDK.
- `demo_server.py` — a local HTTP demo with synthetic responses; no Unkey account needed.

This is an integration-example fix, not a change to Unkey's API or the SDK.

## Run it

Python 3.11+ (tested on 3.13).

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock.txt
python reproduce.py
python -m pytest -q
```

Expected `reproduce.py` output:

```text
Current docs: status=429; rate-limit headers={}
Minimal patch: status=429; rate-limit headers={'x-ratelimit-limit': '10', 'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1800000060'}
Async example: status=429; rate-limit headers={'x-ratelimit-limit': '10', 'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1800000060'}
```

The values are synthetic fixtures, not a live Unkey response. `httpx.MockTransport` intercepts the SDK's HTTP calls before they leave the machine. The SDK still builds a real request and parses a real response model.

### Local HTTP demo

```bash
uvicorn demo_server:app --host 127.0.0.1 --port 8091
```

In another terminal:

```bash
curl -i -H 'Authorization: Bearer demo-limited' http://127.0.0.1:8091/items
curl -i -H 'Authorization: Bearer demo-valid' http://127.0.0.1:8091/items
```

`demo-limited` returns 429 with the rate-limit headers; `demo-valid` returns 200. Other synthetic keys return 401. The demo never contacts Unkey.

### Against a real Unkey account (optional)

For `uvicorn app:app`, set `UNKEY_ROOT_KEY` in your environment. The cookbook says the root key needs permission to verify keys. Don't commit the key. The app refuses to start without one.

## Tests

`tests/test_app.py` covers:

- the original snippet dropping rate-limit headers on a 429, and the patched snippet keeping them
- the async example keeping headers on success and on each documented denial code
- missing or malformed bearer auth, with no call to Unkey
- upstream 429s vs an end-customer 429
- timeouts, connection errors, and malformed responses failing closed as 503, without leaking SDK error text or retrying
- permission forwarding, missing rate limits, and an unknown future denial code

One Starlette deprecation warning may appear: current Starlette recommends `httpx2` for its TestClient. It does not fail the tests.

## What `rl.reset` means

The cookbook treats `rl.reset` as a Unix timestamp in milliseconds and divides by 1000 for `X-RateLimit-Reset`, which is conventionally seconds:

```python
# rl.reset is a Unix timestamp in milliseconds; the header is conventionally seconds.
headers["X-RateLimit-Reset"] = str(rl.reset // 1000)
```

A live `keys.verifyKey` run on 12 November 2026 confirmed that. This example keeps the cookbook's conversion and does not add a `Retry-After` header.

The [keys.verifyKey API reference](https://www.unkey.com/docs/platform/api-reference/keys/verify-api-key.md) still describes the same field as "Rate limit reset duration in milliseconds," with example `3600000` and a maximum of `2592000000`. Those look like duration bounds, and they would not fit a real timestamp. The official Python SDK copies that wording onto `VerifyKeyRatelimitData.reset`.

Elsewhere, Unkey already describes `reset` as a timestamp:

- [How rate limiting works](https://www.unkey.com/docs/api-management/ratelimiting/how-it-works.md): "`reset` in the body is Unix milliseconds" and "Unix milliseconds when the current window ends."
- [ratelimit.limit](https://www.unkey.com/docs/platform/api-reference/ratelimit/apply-rate-limiting.md): "The Unix timestamp in milliseconds when the rate limit window will reset."
- [Verifying keys](https://www.unkey.com/docs/api-management/keys/verifying-keys.md): `reset` (Unix milliseconds).

### Live results (12 November 2026, IST)

Against a live test key, with two auto-applied limits (3 per 60s, 20 per 1h):

- `keys.verifyKey` was called through `unkey.py` and raw `POST /v2/keys.verifyKey`.
- The first three calls were valid (`remaining` 2, 1, then 0). The fourth and later calls returned `code=RATE_LIMITED`.
- `ratelimits[].reset` was a Unix timestamp in milliseconds, not a duration. The 60s window stayed at `1794483720000` (17:12:00 IST) and the 1h window stayed at `1794484800000` (17:30:00 IST) across every call. Those values did not count down. What shrank was `reset` minus the local time, in line with a fixed end-of-window timestamp. The times themselves look aligned to UTC clock boundaries (the next minute and the next hour).
- The async example in this repo, pointed at the same live API, returned 429 with `X-RateLimit-Limit: 3`, `X-RateLimit-Remaining: 0`, and `X-RateLimit-Reset: 1794483720`. That header is the timestamp in seconds, 48 seconds after the call, which is the sensible result of `rl.reset // 1000`.

`ratelimit.limit` was not called in this run: the workspace had no rate-limit namespace, and creating one needed a write permission the test credential did not have. The published `ratelimit.limit` docs already treat `reset` as a Unix millisecond timestamp.
