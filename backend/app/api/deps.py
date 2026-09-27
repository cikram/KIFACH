"""Shared API dependencies."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.services.jobs import JobManager, get_job_manager
from app.services.storage import Store


def settings_dep() -> Settings:
    return get_settings()


def store_dep() -> Store:
    return Store(get_settings())


def jobs_dep() -> JobManager:
    return get_job_manager()
