"""Teach, review, publish, and start verification."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import jobs_dep, settings_dep, store_dep
from app.api.errors import ApiError, bad_request, conflict, not_found
from app.config import Settings
from app.domain.models import (
    Attempt,
    AttemptStatus,
    OrderingRule,
    SkillGraph,
    SkillStatus,
    SkillSummary,
    Step,
    ValidationResult,
)
from app.domain.skill_graph import apply_review, publish, validate_procedure
from app.providers import provider_label
from app.services.jobs import Job, JobManager
from app.services.observation_extractor import engine_config, run_verify
from app.services.skill_compiler import run_teach
from app.services.storage import NotFound, Store, is_safe_id, new_id

router = APIRouter(tags=["skills"])


class TeachRequest(BaseModel):
    video_id: str
    task_hint: str = Field(default="", max_length=400)


class JobAccepted(BaseModel):
    job_id: str
    events_url: str


class SkillUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    objects: list[str] | None = None
    steps: list[Step] | None = None
    rules: list[OrderingRule] | None = None
    confirmed_rule_ids: list[str] | None = None
    reviewer_note: str | None = None
    mark_reviewed: bool = False


class PublishResponse(BaseModel):
    skill: SkillGraph | None
    validation: ValidationResult


class AttemptRequest(BaseModel):
    video_id: str
    mode: str = Field(default="upload", pattern="^(upload|live)$")


def _get_skill(store: Store, skill_id: str) -> SkillGraph:
    if not is_safe_id(skill_id):
        raise bad_request("invalid_id", "That skill id is not valid.")
    try:
        return store.get_skill(skill_id)
    except NotFound as exc:
        raise not_found(f"No skill with id {skill_id}.") from exc


@router.post("/skills/teach", response_model=JobAccepted, status_code=202)
async def teach(
    request: TeachRequest,
    settings: Settings = Depends(settings_dep),
    store: Store = Depends(store_dep),
    jobs: JobManager = Depends(jobs_dep),
) -> JobAccepted:
    if not is_safe_id(request.video_id):
        raise bad_request("invalid_id", "That video id is not valid.")
    if not store.exists("videos", request.video_id):
        raise not_found(f"No uploaded video with id {request.video_id}.")

    job = jobs.create("teach")

    async def work(current: Job) -> None:
        await run_teach(
            current,
            jobs,
            request.video_id,
            task_hint=request.task_hint,
            settings=settings,
            store=store,
        )

    await jobs.run(job, work)
    return JobAccepted(job_id=job.job_id, events_url=f"/api/jobs/{job.job_id}/events")


@router.get("/skills", response_model=list[SkillSummary])
async def list_skills(store: Store = Depends(store_dep)) -> list[SkillSummary]:
    summaries: list[SkillSummary] = []
    for skill in sorted(store.list_skills(), key=lambda s: s.created_at, reverse=True):
        latest = store.latest_attempt(skill.skill_id)
        summaries.append(
            SkillSummary(
                skill_id=skill.skill_id,
                title=skill.title,
                summary=skill.summary,
                status=skill.status,
                step_count=len(skill.steps),
                rule_count=len(skill.rules),
                created_at=skill.created_at,
                source_video_id=skill.source_video_id,
                provenance=skill.provenance,
                reviewed=skill.review.reviewed,
                last_attempt_id=latest.attempt_id if latest else None,
                last_verdict=latest.verdict if latest else None,
            )
        )
    return summaries


@router.get("/skills/{skill_id}", response_model=SkillGraph)
async def get_skill(skill_id: str, store: Store = Depends(store_dep)) -> SkillGraph:
    return _get_skill(store, skill_id)


@router.get("/skills/{skill_id}/validation", response_model=ValidationResult)
async def validate_skill(
    skill_id: str, store: Store = Depends(store_dep)
) -> ValidationResult:
    return validate_procedure(_get_skill(store, skill_id))


@router.put("/skills/{skill_id}", response_model=SkillGraph)
async def update_skill(
    skill_id: str, update: SkillUpdate, store: Store = Depends(store_dep)
) -> SkillGraph:
    skill = _get_skill(store, skill_id)
    if skill.status is SkillStatus.PUBLISHED:
        raise conflict(
            "already_published",
            "A published procedure cannot be edited. Teach a new version instead.",
        )
    revised = apply_review(
        skill,
        steps=update.steps,
        rules=update.rules,
        title=update.title,
        summary=update.summary,
        objects=update.objects,
        confirmed_rule_ids=update.confirmed_rule_ids,
        reviewer_note=update.reviewer_note,
        mark_reviewed=update.mark_reviewed,
    )
    store.save_skill(revised)
    return revised


@router.post("/skills/{skill_id}/publish", response_model=PublishResponse)
async def publish_skill(
    skill_id: str, store: Store = Depends(store_dep)
) -> PublishResponse:
    skill = _get_skill(store, skill_id)
    if skill.status is SkillStatus.PUBLISHED:
        return PublishResponse(
            skill=skill, validation=ValidationResult(ok=True, issues=[])
        )
    published, result = publish(skill)
    if published is None:
        return PublishResponse(skill=None, validation=result)
    store.save_skill(published)
    return PublishResponse(skill=published, validation=result)


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, store: Store = Depends(store_dep)) -> None:
    _get_skill(store, skill_id)
    store.delete_skill(skill_id)


@router.post("/skills/{skill_id}/attempts", response_model=JobAccepted, status_code=202)
async def start_attempt(
    skill_id: str,
    request: AttemptRequest,
    settings: Settings = Depends(settings_dep),
    store: Store = Depends(store_dep),
    jobs: JobManager = Depends(jobs_dep),
) -> JobAccepted:
    skill = _get_skill(store, skill_id)
    if skill.status is not SkillStatus.PUBLISHED:
        raise conflict(
            "skill_not_published",
            f"{skill.title} is still a draft. Review and publish it before "
            "verifying an attempt.",
        )
    if not is_safe_id(request.video_id):
        raise bad_request("invalid_id", "That video id is not valid.")
    if not store.exists("videos", request.video_id):
        raise not_found(f"No uploaded video with id {request.video_id}.")

    attempt = Attempt(
        attempt_id=new_id("att"),
        skill_id=skill_id,
        media_id=request.video_id,
        mode="live" if request.mode == "live" else "upload",
        config=engine_config(settings, request.mode),
        status=AttemptStatus.RUNNING,
    )
    store.save_attempt(attempt)

    job = jobs.create("verify")
    jobs.emit(
        job,
        "attempt_created",
        attempt_id=attempt.attempt_id,
        skill_id=skill_id,
        provider_label=provider_label(settings),
    )

    async def work(current: Job) -> None:
        try:
            await run_verify(
                current, jobs, attempt, settings=settings, store=store
            )
        except Exception:
            failed = attempt.model_copy(
                update={"status": AttemptStatus.FAILED, "error": "Verification failed."}
            )
            store.save_attempt(failed)
            raise

    await jobs.run(job, work)
    return JobAccepted(job_id=job.job_id, events_url=f"/api/jobs/{job.job_id}/events")
