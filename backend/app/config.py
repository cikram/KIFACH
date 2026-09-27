"""Runtime configuration, read once from the environment.

Every tunable the pipelines use is here so a run can be described by its
settings, and so tests can build an isolated settings object instead of
mutating global state.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "0.1.0"

REPO_ROOT = Path(__file__).resolve().parents[2]

ProviderName = Literal["nvidia", "openai_compat", "mock"]
CacheMode = Literal["on", "off", "replay"]


class Settings(BaseSettings):
    """Environment-backed settings. Prefix-free names match the documented env vars."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- provider selection -------------------------------------------------
    kifach_provider: str = Field(default="", alias="KIFACH_PROVIDER")
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL"
    )
    openai_compat_base_url: str = Field(default="", alias="OPENAI_COMPAT_BASE_URL")
    openai_compat_api_key: str = Field(default="", alias="OPENAI_COMPAT_API_KEY")
    # Default chosen from NVIDIA's live catalogue and VLM NIM docs; see
    # BUILD_REPORT.md for the exact sources and the image input format.
    vlm_model: str = Field(
        default="nvidia/cosmos-reason2-8b", alias="KIFACH_VLM_MODEL"
    )

    # --- provider behaviour -------------------------------------------------
    request_timeout_s: float = Field(default=90.0, alias="KIFACH_TIMEOUT_S")
    max_retries: int = Field(default=3, alias="KIFACH_MAX_RETRIES")
    max_concurrency: int = Field(default=2, alias="KIFACH_MAX_CONCURRENCY")
    max_images_per_call: int = Field(default=4, alias="KIFACH_MAX_IMAGES_PER_CALL")
    temperature: float = Field(default=0.0, alias="KIFACH_TEMPERATURE")
    prompt_version: str = Field(default="v1", alias="KIFACH_PROMPT_VERSION")
    cache_mode: str = Field(default="on", alias="KIFACH_CACHE")

    # --- media processing ---------------------------------------------------
    sample_fps: float = Field(default=2.0, alias="KIFACH_FPS")
    frame_size: int = Field(default=768, alias="KIFACH_FRAME_SIZE")
    jpeg_quality: int = Field(default=85, alias="KIFACH_JPEG_QUALITY")
    window_seconds: float = Field(default=4.0, alias="KIFACH_WINDOW_SECONDS")
    window_overlap: float = Field(default=1.0, alias="KIFACH_WINDOW_OVERLAP")
    max_upload_mb: int = Field(default=200, alias="KIFACH_MAX_UPLOAD_MB")

    # --- engine -------------------------------------------------------------
    min_confidence: float = Field(default=0.6, alias="KIFACH_MIN_CONFIDENCE")
    confirmations_required: int = Field(default=1, alias="KIFACH_CONFIRMATIONS")
    live_confirmations_required: int = Field(
        default=2, alias="KIFACH_LIVE_CONFIRMATIONS"
    )
    independent_gap_s: float = Field(default=1.0, alias="KIFACH_INDEPENDENT_GAP_S")

    # --- storage ------------------------------------------------------------
    data_dir: str = Field(default="", alias="KIFACH_DATA_DIR")

    @property
    def data_root(self) -> Path:
        root = Path(self.data_dir) if self.data_dir else REPO_ROOT / "data"
        return root.resolve()

    @property
    def media_root(self) -> Path:
        return self.data_root / "media"

    @property
    def cache_root(self) -> Path:
        return self.data_root / "cache"

    @property
    def frontend_dist(self) -> Path:
        return REPO_ROOT / "frontend" / "dist"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def resolved_cache_mode(self) -> CacheMode:
        mode = self.cache_mode.strip().lower()
        if mode in ("on", "off", "replay"):
            return mode  # type: ignore[return-value]
        return "on"

    def resolved_provider(self) -> ProviderName:
        """Explicit selection wins; otherwise a real NVIDIA key enables NVIDIA."""
        explicit = self.kifach_provider.strip().lower()
        if explicit in ("nvidia", "openai_compat", "mock"):
            return explicit  # type: ignore[return-value]
        if self.nvidia_api_key.strip():
            return "nvidia"
        if self.openai_compat_base_url.strip() and self.openai_compat_api_key.strip():
            return "openai_compat"
        return "mock"

    def ensure_dirs(self) -> None:
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        (self.data_root / "skills").mkdir(parents=True, exist_ok=True)
        (self.data_root / "attempts").mkdir(parents=True, exist_ok=True)
        (self.data_root / "videos").mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    """Used by tests after changing environment variables."""
    get_settings.cache_clear()


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")
