"""Provider selection.

Explicit KIFACH_PROVIDER wins. Otherwise a usable NVIDIA key selects NVIDIA, a
usable OpenAI-compatible endpoint selects that, and everything else falls back
to the clearly labelled mock.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.providers.base import (  # re-exported for callers
    CacheMiss,
    ObserveRequest,
    ProposalRequest,
    ProviderError,
    VisionProvider,
    WindowRequest,
)
from app.providers.http_vlm import HttpVlmProvider
from app.providers.mock import MockProvider

__all__ = [
    "CacheMiss",
    "ObserveRequest",
    "ProposalRequest",
    "ProviderError",
    "VisionProvider",
    "WindowRequest",
    "build_provider",
    "provider_label",
]


def build_provider(settings: Settings | None = None) -> VisionProvider:
    settings = settings or get_settings()
    name = settings.resolved_provider()
    if name == "nvidia":
        return HttpVlmProvider(
            settings,
            name="nvidia",
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
            model=settings.vlm_model,
        )
    if name == "openai_compat":
        return HttpVlmProvider(
            settings,
            name="openai_compat",
            base_url=settings.openai_compat_base_url,
            api_key=settings.openai_compat_api_key,
            model=settings.vlm_model,
        )
    return MockProvider(settings)


def provider_label(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    name = settings.resolved_provider()
    if name == "mock":
        return "MOCK"
    return "CACHED" if settings.resolved_cache_mode() == "replay" else "LIVE"
