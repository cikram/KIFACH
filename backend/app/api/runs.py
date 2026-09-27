"""Attempt results, deterministic replay, and job event streams."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.deps import jobs_dep, settings_dep, store_dep
from app.api.errors import bad_request, not_found
from app.config import Settings
from app.domain.models import Attempt, SkillGraph, Verdict
from app.domain.verifier import replay as replay_engine
from app.services.jobs import JobManager
from app.services.storage import NotFound, Store, is_safe_id

router = APIRouter(tags=["attempts"])


class AttemptDetail(BaseModel):
    attempt: Attempt
    skill: SkillGraph


class ReplayResponse(BaseModel):
    attempt_id: str
    identical: bool
    verdict: Verdict
    previous_verdict: Verdict
    event_count: int
    previous_event_count: int
    differences: list[str]


def _get_attempt(store: Store, attempt_id: str) -> Attempt:
    if not is_safe_id(attempt_id):
        raise bad_request("invalid_id", "That attempt id is not valid.")
    try:
        return store.get_attempt(attempt_id)
    except NotFound as exc:
        raise not_found(f"No attempt with id {attempt_id}.") from exc


@router.get("/attempts", response_model=list[Attempt])
async def list_attempts(store: Store = Depends(store_dep)) -> list[Attempt]:
    return sorted(store.list_attempts(), key=lambda a: a.created_at, reverse=True)


@router.get("/attempts/{attempt_id}", response_model=AttemptDetail)
async def get_attempt(
    attempt_id: str, store: Store = Depends(store_dep)
) -> AttemptDetail:
    attempt = _get_attempt(store, attempt_id)
    try:
        skill = store.get_skill(attempt.skill_id)
    except NotFound as exc:
        raise not_found(
            f"The procedure {attempt.skill_id} this attempt was assessed against no "
            "longer exists."
        ) from exc
    return AttemptDetail(attempt=attempt, skill=skill)


@router.post("/attempts/{attempt_id}/replay", response_model=ReplayResponse)
async def replay_attempt(
    attempt_id: str, store: Store = Depends(store_dep)
) -> ReplayResponse:
    """Re-run the stored observation log through the engine and compare.

    Identical inputs must give identical outputs; a difference here means the
    stored record and the engine have drifted apart, which the UI surfaces
    rather than hiding.
    """
    attempt = _get_attempt(store, attempt_id)
    try:
        skill = store.get_skill(attempt.skill_id)
    except NotFound as exc:
        raise not_found("The procedure for this attempt no longer exists.") from exc

    result = replay_engine(skill, attempt.observations, attempt.config)
    before = [event.model_dump(mode="json") for event in attempt.events]
    after = [event.model_dump(mode="json") for event in result.events]
    differences: list[str] = []
    if result.verdict != attempt.verdict:
        differences.append(
            f"verdict {attempt.verdict.value} -> {result.verdict.value}"
        )
    if before != after:
        differences.append(
            f"event log differs ({len(before)} stored, {len(after)} replayed)"
        )
    if {k: v.value for k, v in result.step_states.items()} != {
        k: v.value for k, v in attempt.step_states.items()
    }:
        differences.append("step states differ")

    return ReplayResponse(
        attempt_id=attempt.attempt_id,
        identical=not differences,
        verdict=result.verdict,
        previous_verdict=attempt.verdict,
        event_count=len(after),
        previous_event_count=len(before),
        differences=differences,
    )


class AttachMedia(BaseModel):
    video_id: str


@router.post("/attempts/{attempt_id}/media", response_model=Attempt)
async def attach_media(
    attempt_id: str, body: AttachMedia, store: Store = Depends(store_dep)
) -> Attempt:
    """Attach a live session's uploaded recording so evidence clicks can seek it."""
    attempt = _get_attempt(store, attempt_id)
    if not is_safe_id(body.video_id):
        raise bad_request("invalid_id", "That video id is not valid.")
    if not store.exists("videos", body.video_id):
        raise not_found(f"No uploaded video with id {body.video_id}.")
    updated = attempt.model_copy(update={"media_id": body.video_id})
    store.save_attempt(updated)
    return updated


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    jobs: JobManager = Depends(jobs_dep),
    settings: Settings = Depends(settings_dep),
) -> EventSourceResponse:
    """Server-sent events for one job, resumable with Last-Event-ID."""
    job = jobs.get(job_id)
    if job is None:
        raise not_found(f"No job with id {job_id}.")

    header = request.headers.get("last-event-id") or request.query_params.get(
        "last_event_id"
    )
    try:
        last_event_id = int(header) if header else 0
    except ValueError:
        last_event_id = 0

    async def generator():
        async for event in jobs.stream(job, last_event_id):
            if await request.is_disconnected():  # pragma: no cover - client hangup
                break
            yield {
                "id": str(event.id),
                "event": event.type,
                "data": json.dumps(event.as_dict()),
            }

    return EventSourceResponse(generator())


@router.get("/jobs/{job_id}")
async def job_state(job_id: str, jobs: JobManager = Depends(jobs_dep)) -> dict:
    """The whole event list, so a refreshed page can recover without a stream."""
    job = jobs.get(job_id)
    if job is None:
        raise not_found(f"No job with id {job_id}.")
    return job.as_dict()
