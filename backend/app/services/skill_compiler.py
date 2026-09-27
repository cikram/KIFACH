"""The teach pipeline: expert media in, reviewable draft procedure out.

The model's job ends at the proposal. Everything after it is validation and
human review: a proposal that fails validation gets one bounded repair pass and
is then saved as a flagged draft for the expert to fix, never published and
never silently trimmed.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings, get_settings
from app.domain.models import (
    GraphProposal,
    Provenance,
    SkillGraph,
    SkillStatus,
    VideoMeta,
    WindowDescription,
)
from app.domain.skill_graph import repair_proposal, validate_procedure
from app.providers import ProposalRequest, ProviderError, WindowRequest, build_provider
from app.providers.base import VisionProvider
from app.services.jobs import Job, JobManager
from app.services.storage import Store, new_id
from app.services.video import (
    evidence_for_window,
    extract_frames,
    pick_frames,
    window_frames,
)

log = logging.getLogger("kifach.teach")


async def describe_windows(
    provider: VisionProvider,
    video: VideoMeta,
    windows: list,
    settings: Settings,
    *,
    task_hint: str = "",
    on_window=None,
) -> tuple[list[WindowDescription], list[str]]:
    """Describe every window, keeping failures as explicit limitations."""
    descriptions: list[WindowDescription] = []
    limitations: list[str] = []
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))

    async def one(window) -> tuple[int, WindowDescription | None, str | None]:
        frames = pick_frames(window_frames(video, window), settings.max_images_per_call)
        async with semaphore:
            try:
                description = await provider.describe_expert_window(
                    WindowRequest(
                        video=video, window=window, frames=frames, task_hint=task_hint
                    )
                )
                return window, description, None
            except ProviderError as exc:
                return window, None, str(exc)

    results = await asyncio.gather(*(one(window) for window in windows))
    for window, description, error in results:
        if description is not None:
            descriptions.append(description)
            if on_window:
                on_window(description)
        else:
            message = (
                f"The window {window.t_start:.1f}s-{window.t_end:.1f}s could not be "
                f"analysed: {error}"
            )
            limitations.append(message)
            fallback = WindowDescription(
                window_id=window.window_id,
                t_start=window.t_start,
                t_end=window.t_end,
                limitations=[message],
                evidence=evidence_for_window(video, window),
                provenance=Provenance.MOCK,
            )
            descriptions.append(fallback)
            if on_window:
                on_window(fallback)
    descriptions.sort(key=lambda d: (d.t_start, d.window_id))
    return descriptions, limitations


def proposal_to_graph(
    proposal: GraphProposal,
    video: VideoMeta,
    *,
    provenance: Provenance,
    skill_id: str | None = None,
) -> SkillGraph:
    return SkillGraph(
        skill_id=skill_id or new_id("skill"),
        title=proposal.title,
        summary=proposal.summary,
        source_video_id=video.video_id,
        status=SkillStatus.DRAFT,
        objects=proposal.objects,
        steps=proposal.steps,
        rules=proposal.rules,
        provenance=provenance,
    )


async def run_teach(
    job: Job,
    manager: JobManager,
    video_id: str,
    *,
    task_hint: str = "",
    settings: Settings | None = None,
    store: Store | None = None,
    provider: VisionProvider | None = None,
) -> SkillGraph:
    settings = settings or get_settings()
    store = store or Store(settings)
    provider = provider or build_provider(settings)
    owns_provider = provider is not None

    video = store.get_video(video_id)
    manager.emit(
        job,
        "extraction_started",
        video_id=video.video_id,
        filename=video.filename,
    )
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
        frames=[
            {"index": f.index, "timestamp_s": f.timestamp_s, "media_path": f.media_path}
            for f in video.frames
        ],
    )

    try:
        def report(description: WindowDescription) -> None:
            manager.emit(
                job,
                "window_analysed",
                window_id=description.window_id,
                t_start=description.t_start,
                t_end=description.t_end,
                objects=description.objects,
                actions=description.actions,
                changes=description.changes,
                candidate_steps=description.candidate_steps,
                limitations=description.limitations,
                provenance=description.provenance.value,
            )

        descriptions, limitations = await describe_windows(
            provider,
            video,
            extraction.windows,
            settings,
            task_hint=task_hint,
            on_window=report,
        )

        usable = [d for d in descriptions if d.objects or d.actions or d.candidate_steps]
        if not usable:
            raise ProviderError(
                "No window of this video could be described, so there is nothing to "
                "propose a procedure from. "
                + (limitations[0] if limitations else "")
            )

        manager.emit(job, "proposal_started", window_count=len(usable))
        key_frames = pick_frames(video.frames, settings.max_images_per_call)
        proposal = await provider.propose_graph(
            ProposalRequest(
                video=video,
                descriptions=descriptions,
                key_frames=key_frames,
                task_hint=task_hint,
            )
        )
    finally:
        if owns_provider:
            await provider.aclose()

    provenance = Provenance.MOCK
    for description in descriptions:
        if description.provenance is not Provenance.MOCK:
            provenance = description.provenance
            break

    graph = proposal_to_graph(proposal, video, provenance=provenance)
    result = validate_procedure(graph)
    flags: list[str] = []
    if not result.ok:
        manager.emit(
            job,
            "validation_repairing",
            issues=[issue.model_dump() for issue in result.issues],
        )
        repaired = repair_proposal(proposal, result.issues)
        graph = proposal_to_graph(
            repaired, video, provenance=provenance, skill_id=graph.skill_id
        )
        result = validate_procedure(graph)
        if not result.ok:
            flags = [issue.message for issue in result.issues]

    if limitations:
        flags.extend(limitations)
    graph = graph.model_copy(update={"validation_flags": flags})

    store.save_skill(graph)
    manager.emit(
        job,
        "validation_complete",
        skill_id=graph.skill_id,
        ok=result.ok,
        issues=[issue.model_dump() for issue in result.issues],
        flags=flags,
    )
    manager.finish(
        job,
        skill_id=graph.skill_id,
        status=graph.status.value,
        provenance=graph.provenance.value,
        needs_attention=bool(flags),
    )
    return graph
