"""Shared fixtures. Every test runs on the mock provider with its own data dir."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

SAMPLES = REPO_ROOT / "samples"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Give each test its own data directory and force the offline provider."""
    monkeypatch.setenv("KIFACH_PROVIDER", "mock")
    monkeypatch.setenv("KIFACH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_COMPAT_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.setenv("KIFACH_CACHE", "on")

    from app.config import get_settings, reset_settings_cache
    from app.services.jobs import reset_job_manager

    reset_settings_cache()
    reset_job_manager()
    settings = get_settings()
    settings.ensure_dirs()
    yield settings
    reset_settings_cache()
    reset_job_manager()


@pytest.fixture
def store(isolated_settings):
    from app.services.storage import Store

    return Store(isolated_settings)


@pytest.fixture
def client(isolated_settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def samples_present() -> bool:
    return (SAMPLES / "expert.webm").exists()


def sample_path(name: str) -> Path:
    path = SAMPLES / name
    if not path.exists():
        pytest.skip(
            f"{path} is missing. Generate the fixtures with: "
            "python scripts/make_synthetic_video.py"
        )
    return path


def require_env_clean() -> None:
    assert "NVIDIA_API_KEY" not in os.environ
