"""Health and provider status.

This reports local configuration only. It never makes a model call, so the UI
can poll it cheaply; `POST /api/health/provider-check` is the explicit, opt-in
connectivity test.
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends

from app.config import VERSION, Settings
from app.domain.models import HealthResponse
from app.api.deps import settings_dep
from app.providers import build_provider

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(settings_dep)) -> HealthResponse:
    provider = build_provider(settings)
    try:
        status = provider.health()
    finally:
        await provider.aclose()
    return HealthResponse(
        status="ok",
        version=VERSION,
        provider=status,
        media_root=str(settings.media_root),
        frontend_built=settings.frontend_dist.exists(),
    )


@router.post("/health/provider-check")
async def provider_check(settings: Settings = Depends(settings_dep)) -> dict:
    """An explicit connectivity check against the configured provider."""
    name = settings.resolved_provider()
    if name == "mock":
        return {
            "provider": "mock",
            "reachable": True,
            "detail": "The mock provider is local and always reachable.",
        }
    if settings.resolved_cache_mode() == "replay":
        return {
            "provider": name,
            "reachable": False,
            "detail": "Replay mode makes no network calls by design.",
        }
    base = (
        settings.nvidia_base_url
        if name == "nvidia"
        else settings.openai_compat_base_url
    )
    key = (
        settings.nvidia_api_key
        if name == "nvidia"
        else settings.openai_compat_api_key
    )
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        return {
            "provider": name,
            "reachable": response.status_code < 500,
            "status_code": response.status_code,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "model": settings.vlm_model,
            "detail": (
                "Endpoint answered."
                if response.status_code < 400
                else f"Endpoint answered HTTP {response.status_code}."
            ),
        }
    except httpx.HTTPError as exc:
        return {
            "provider": name,
            "reachable": False,
            "detail": f"{exc.__class__.__name__}: could not reach {base}.",
        }
