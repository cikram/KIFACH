"""API router assembly."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health, live, runs, skills, videos

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(videos.router)
api_router.include_router(skills.router)
api_router.include_router(runs.router)
api_router.include_router(live.router)

__all__ = ["api_router"]
