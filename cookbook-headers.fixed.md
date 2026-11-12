> ## Documentation Index
> Fetch the complete documentation index at: https://www.unkey.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

> ## Agent Instructions
> Unkey is two separate products. Compute builds, deploys, and runs apps behind a gateway. API Management issues API keys, enforces rate limits, manages identities and permissions, and reports usage. Say which product a page belongs to; a reader can use either without the other.
> Every Unkey API endpoint is an HTTP POST to https://api.unkey.com/v2/{service}.{procedure} with a root key in the Authorization: Bearer header. Root keys are workspace scoped.
> Error codes have the form err:{system}:{category}:{specific} and each has a page at /errors/{system}/{category}/{specific}.
> The word environment means production or preview in Compute. Rate limiting has four meanings on this site; the glossary lists them.

# FastAPI authentication

> Verify API keys in FastAPI with a typed dependency.

**Outcome:** a route adds `Depends(require_key())` or `Depends(require_key("reports.read"))`, and the dependency verifies (Here: keys.verifyKey checking a key your user presented. Not domain verification and not the gateway policy.) the key, rejects bad requests with the right status, gives the handler the verification data, and adds `X-RateLimit-*` headers.

> [!NOTE]
>
> Create a root key with the permissions listed on this page under **Root Keys** in the dashboard sidebar. CLI commands can instead use a session from [unkey login](https://www.unkey.com/docs/platform/cli/login.md) with the required permissions. See [Permission reference](https://www.unkey.com/docs/platform/root-keys/permissions-legacy.md) for every permission.

The root key needs `api.*.verify_key`. Install with `pip install unkey.py fastapi uvicorn`.

## The dependency

`require_key` takes an optional permission query, so each route can ask for its own. FastAPI's `HTTPBearer` reads the header and returns 401 if it's missing.

Catch `httpx.HTTPError` as well as `errors.UnkeyError`. A timeout or connection failure raises an `httpx` error, and without catching it an outage becomes a 500 instead of a 503.

```python app/auth.py theme={"system"}
import os
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from unkey.py import Unkey, errors, models

unkey = Unkey(root_key=os.environ["UNKEY_ROOT_KEY"])
bearer = HTTPBearer(auto_error=True)

STATUS = {
    "RATE_LIMITED": 429,
    "USAGE_EXCEEDED": 402,
    "FORBIDDEN": 403,
    "INSUFFICIENT_PERMISSIONS": 403,
}


def require_key(permissions: str | None = None):
    def dependency(
        response: Response,
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    ) -> models.V2KeysVerifyKeyResponseData:
        try:
            res = unkey.keys.verify_key(key=credentials.credentials, permissions=permissions)
        except (errors.UnkeyError, httpx.HTTPError) as e:
            raise HTTPException(status_code=503, detail="authentication unavailable") from e

        data = res.data
        headers = {}
        if data.ratelimits:
            # Report the tightest limit that was checked.
            rl = min(data.ratelimits, key=lambda r: r.remaining)
            headers["X-RateLimit-Limit"] = str(rl.limit)
            headers["X-RateLimit-Remaining"] = str(rl.remaining)
            # rl.reset is a Unix timestamp in milliseconds; the header is conventionally seconds.
            headers["X-RateLimit-Reset"] = str(rl.reset // 1000)

        if not data.valid:
            code = data.code
            raise HTTPException(status_code=STATUS.get(code, 401), detail=code, headers=headers)
        response.headers.update(headers)
        return data

    return dependency
```

## Routes

```python app/main.py theme={"system"}
from typing import Annotated

from fastapi import Depends, FastAPI
from unkey.py import models

from .auth import require_key

app = FastAPI()


@app.get("/items")
def list_items(verification: Annotated[models.V2KeysVerifyKeyResponseData, Depends(require_key())]):
    owner = verification.identity.external_id if verification.identity else None
    return {"items": [], "owner": owner, "credits_left": verification.credits}


@app.get("/reports")
def reports(verification: Annotated[models.V2KeysVerifyKeyResponseData, Depends(require_key("reports.read"))]):
    return {"reports": [], "key": verification.key_id}
```

Headers set on the injected `Response` reach the client when the request succeeds. When the dependency raises an `HTTPException`, such as a 429, those headers are dropped, so pass them in the exception's `headers` argument if you need them on rejections too.

## Async

For an async application, use `async with Unkey(...)` in the lifespan and `await unkey.keys.verify_key_async(...)` in an `async def` dependency. The rest of the code is unchanged.

## Related

* [Python guide](https://www.unkey.com/docs/api-management/guides/python.md) for creating keys and the basic flow.
* [Verifying keys](https://www.unkey.com/docs/api-management/keys/verifying-keys.md) for every response field.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.