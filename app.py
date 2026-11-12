"""Runnable, async version of Unkey's FastAPI cookbook (SDK 3.2.4)."""
import os
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from unkey.py import Unkey, errors, models

STATUS = {
    "RATE_LIMITED": 429,
    "USAGE_EXCEEDED": 402,
    "FORBIDDEN": 403,
    "INSUFFICIENT_PERMISSIONS": 403,
}
bearer = HTTPBearer(auto_error=False)


def rate_headers(data: models.V2KeysVerifyKeyResponseData) -> dict[str, str]:
    """Follow the cookbook's reset convention; do not invent Retry-After semantics."""
    if not data.ratelimits:
        return {}
    rl = min(data.ratelimits, key=lambda r: r.remaining)
    return {
        "X-RateLimit-Limit": str(rl.limit),
        "X-RateLimit-Remaining": str(rl.remaining),
        "X-RateLimit-Reset": str(rl.reset // 1000),
    }


def require_key(permissions: str | None = None):
    async def dependency(
        request: Request,
        response: Response,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> models.V2KeysVerifyKeyResponseData:
        if credentials is None:
            raise HTTPException(401, "missing bearer key", headers={"WWW-Authenticate": "Bearer"})
        try:
            # No retries: verification can consume credits and rate-limit tokens.
            result = await request.app.state.unkey.keys.verify_key_async(
                key=credentials.credentials, permissions=permissions,
                retries=None, timeout_ms=2000,
            )
        except (errors.UnkeyError, errors.NoResponseError, httpx.HTTPError) as exc:
            # Never return SDK error text: it can contain request details.
            raise HTTPException(503, "authentication unavailable") from exc
        data = result.data
        headers = rate_headers(data)
        if not data.valid:
            status = STATUS.get(data.code, 401)
            if status == 401:
                headers["WWW-Authenticate"] = "Bearer"
            # Headers on the injected Response are lost on HTTPException.
            raise HTTPException(status, str(data.code), headers=headers)
        response.headers.update(headers)
        return data
    return dependency


def create_app(*, root_key: str | None = None, transport=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        key = root_key if root_key is not None else os.environ.get("UNKEY_ROOT_KEY", "")
        if not key:
            raise RuntimeError("UNKEY_ROOT_KEY must be set; no anonymous fallback")
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            async with Unkey(root_key=key, async_client=client, retry_config=None, timeout_ms=2000) as sdk:
                application.state.unkey = sdk
                yield

    application = FastAPI(lifespan=lifespan)

    @application.get("/items")
    async def items(verification: Annotated[models.V2KeysVerifyKeyResponseData, Depends(require_key())]):
        owner = verification.identity.external_id if verification.identity else None
        return {"items": [], "owner": owner, "credits_left": verification.credits}

    @application.get("/reports")
    async def reports(verification: Annotated[models.V2KeysVerifyKeyResponseData, Depends(require_key("reports.read"))]):
        return {"reports": [], "key": verification.key_id}

    return application


app = create_app()
