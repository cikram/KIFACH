"""The verify pipeline: learner media in, evidence-linked assessment out.

The provider is asked only what is visible in each window. Observations are then
normalized, de-duplicated, and fed to the deterministic engine in source-time
order. The engine is re-run over the growing log after each window so the UI can
follow along, which also guarantees that the streamed result and a later replay
of the stored log are the same computation.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings, get_settings
from app.domain.models import (
    Attempt,
    AttemptStatus,
    EngineConfig,
    Observation,
    ObservationStatus,
    Provenance,
    SkillGraph,
    SkillStatus,
    VideoMeta,
    Window,
)
from app.domain.verifier import assess_attempt, observation_sort_key
from app.providers import ObserveRequest, ProviderError, build_provider
from app.providers.base import VisionProvider
from app.services.jobs import Job, JobManager
from app.services.storage import Store
from app.services.video import extract_frames, pick_frames, window_frames

log = logging.getLogger("kifach.verify")

DEDUPE_WINDOW_S = 0.25


def engine_config(settings: Settings, mode: str = "upload") -> EngineConfig:
    return EngineConfig(
        min_confidence=settings.min_confidence,
        confirmations_required=settings.confirmations_required,
        live_confirmations_required=settings.live_confirmations_required,
        independent_gap_s=settings.independent_gap_s,
        mode="live" if mode == "live" else "upload",
    )


def normalize(observations: list[Observation]) -> list[Observation]:
    """Collapse the same visible event reported by two overlapping windows.

    Two observations are the same event when they concern one step, agree on
    status, and start within a quarter second of each other. The more confident
    one survives, so an overlap cannot manufacture a second confirmation.
    """
    ordered = sorted(observations, key=observation_sort_key)
    kept: list[Observation] = []
    for observation in ordered:
        duplicate_index = None
        for index, existing in enumerate(kept):
            if (
                existing.step_id == observation.step_id
                and existing.status == observation.status
                and abs(existing.t_start - observation.t_start) <= DEDUPE_WINDOW_S
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            kept.append(observation)
        elif observation.confidence > kept[duplicate_index].confidence:
            kept[duplicate_index] = observation
    return sorted(kept, key=observation_sort_key)


async def observe_windows(
    provider: VisionProvider,
    video: VideoMeta,
    windows: list[Window],
    skill: SkillGraph,
    settings: Settings,
    *,
    on_window=None,
) -> tuple[list[Observation], list[str]]:
    observations: list[Observation] = []
    limitations: list[str] = []
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    async def one(window: Window):
        frames = pick_frames(window_frames(video, window), settings.max_images_per_call)
        async with semaphore:
            try:
                found = await provider.observe_learner_window(
                    ObserveRequest(
                        video=video,
                        window=window,
                        frames=frames,
                        steps=skill.steps,
                        skill_title=skill.title,
                        checkpoints={s.step_id: s.checkpoint for s in skill.steps},
                    )
                )
                return window, found, None
            except ProviderError as exc:
                return window, [], str(exc)

    results = await asyncio.gather(*(one(window) for window in windows))
    for window, found, error in sorted(results, key=lambda r: r[0].t_start):
        if error is not None:
            limitations.append(
                f"The window {window.t_start:.1f}s-{window.t_end:.1f}s could not be "
                f"analysed: {error}"
            )
        observations.extend(found)
        if on_window:
            on_window(window, found, error)
    return observations, limitations


def apply_engine(
    attempt: Attempt, skill: SkillGraph, observations: list[Observation]
) -> Attempt:
    """Run the engine over an observation log and fold the result into an attempt."""
    result = assess_attempt(skill, observations, attempt.config)
    return attempt.model_copy(
        update={
            "observations": observations,
            "events": result.events,
            "step_states": result.step_states,
            "alerts": result.alerts,
            "verdict": result.verdict,
            "reasons": result.reasons,
        }
    )


async def run_verify(
    job: Job,
    manager: JobManager,
    attempt: Attempt,
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    provider: VisionProvider | None = None,
) -> Attempt:
    settings = settings or get_settings()
    store = store or Store(settings)
    provider = provider or build_provider(settings)

    skill = store.get_skill(attempt.skill_id)
    if skill.status is not SkillStatus.PUBLISHED:
        raise ProviderError(
            f"{skill.title} is still a draft. Review and publish it before "
            "verifying an attempt against it."
        )
    video = store.get_video(attempt.media_id or "")

    manager.emit(job, "extraction_started", video_id=video.video_id)
    extraction = extract_frames(video, settings, store)
    video = extraction.video
    manager.emit(
        job,
        "extraction_complete",
        video_id=video.video_id,
        frame_count=len(video.frames),
        window_count=len(extraction.windows),
        duration_s=video.duration_s,
        limitations=extraction.limitations,
    )

    collected: list[Observation] = []
    emitted_events = 0
    current = attempt

    def report(window: Window, found: list[Observation], error: str | None) -> None:
        nonlocal collected, emitted_events, current
        collected.extend(found)
        manager.emit(
            job,
            "window_observed",
            window_id=window.window_id,
            t_start=window.t_start,
            t_end=window.t_end,
            error=error,
            observations=[o.model_dump(mode="json") for o in found],
        )
        current = apply_engine(current, skill, normalize(collected))
        for event in current.events[emitted_events:]:
            manager.emit(job, "engine_event", **event.model_dump(mode="json"))
        emitted_events = len(current.events)
        manager.emit(
            job,
            "state_updated",
            step_states={k: v.value for k, v in current.step_states.items()},
            alerts=[a.model_dump(mode="json") for a in current.alerts],
        )

    try:
        observations, limitations = await observe_windows(
            provider, video, extraction.windows, skill, settings, on_window=report
        )
    finally:
        await provider.aclose()

    limitations = list(extraction.limitations) + limitations
    provenance = Provenance.MOCK
    for observation in observations:
        if observation.provenance is not Provenance.MOCK:
            provenance = observation.provenance
            break

    if not observations:
        limitations.append(
            "No window of this video produced a usable observation, so this "
            "attempt cannot be assessed from it."
        )

    final = apply_engine(current, skill, normalize(observations))
    final = final.model_copy(
        update={
            "status": AttemptStatus.COMPLETE,
            "limitations": limitations,
            "provenance": provenance,
        }
    )
    # Emit any engine events the incremental pass did not already send.
    for event in final.events[emitted_events:]:
        manager.emit(job, "engine_event", **event.model_dump(mode="json"))

    store.save_attempt(final)
    manager.finish(
        job,
        attempt_id=final.attempt_id,
        skill_id=final.skill_id,
        verdict=final.verdict.value,
        provenance=final.provenance.value,
    )
    return final


def observation_summary(observations: list[Observation]) -> dict[str, int]:
    counts = {status.value: 0 for status in ObservationStatus}
    for observation in observations:
        counts[observation.status.value] += 1
    return counts
