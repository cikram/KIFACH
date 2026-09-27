"""The offline mock provider.

Everything it returns is scripted, deterministic, and labelled MOCK. It exists
for automated tests and for Demo Mode, which must work with no network and must
never look like a live model result.

A mock answer is only produced for media it can identify: an explicit scenario
id, a sha256 listed in `samples/scenarios.json`, or a recognisable sample
filename. For anything else it refuses rather than inventing an assessment.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.domain.models import (
    GraphProposal,
    Observation,
    ObservationStatus,
    Provenance,
    ProviderHealth,
    Step,
    VideoMeta,
    WindowDescription,
)
from app.providers.base import (
    ObserveRequest,
    ProposalRequest,
    ProviderError,
    WindowRequest,
)
from app.providers.scenarios import (
    SCENARIOS,
    STEP_KEYWORDS,
    PROPOSAL,
    Scenario,
    scenario_from_filename,
)

UNSCRIPTED_MESSAGE = (
    "Demo Mode has no scripted analysis for this file. Use one of the bundled "
    "sample videos in samples/, or configure a real provider with NVIDIA_API_KEY "
    "(or OPENAI_COMPAT_BASE_URL) and restart."
)


def load_registry(settings: Settings) -> dict[str, str]:
    """sha256 -> scenario id, from samples/scenarios.json when it exists."""
    from app.config import REPO_ROOT

    path = Path(REPO_ROOT) / "samples" / "scenarios.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    videos = data.get("videos", {})
    registry: dict[str, str] = {}
    for entry in videos.values() if isinstance(videos, dict) else []:
        if isinstance(entry, dict) and entry.get("sha256") and entry.get("scenario"):
            registry[str(entry["sha256"])] = str(entry["scenario"])
    return registry


def map_step_ids(script_ids: list[str], steps: list[Step]) -> dict[str, str]:
    """Map canonical script step ids onto the reviewed procedure's own ids.

    An expert may rename steps during review. Exact ids win; otherwise the
    mapping falls back to keywords in the step title, action, and checkpoint.
    """
    available = {step.step_id: step for step in steps}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for script_id in script_ids:
        if script_id in available:
            mapping[script_id] = script_id
            used.add(script_id)
            continue
        keywords = STEP_KEYWORDS.get(script_id, ())
        for step in steps:
            if step.step_id in used:
                continue
            haystack = " ".join(
                [step.step_id, step.title, step.action, step.checkpoint]
            ).lower()
            if any(keyword in haystack for keyword in keywords):
                mapping[script_id] = step.step_id
                used.add(step.step_id)
                break
    return mapping


class MockProvider:
    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = load_registry(settings)

    # -- scenario resolution ----------------------------------------------

    def resolve(self, video: VideoMeta) -> Scenario | None:
        candidates = [
            video.scenario_hint,
            self.registry.get(video.sha256),
            scenario_from_filename(video.filename),
        ]
        for candidate in candidates:
            if candidate and candidate in SCENARIOS:
                return SCENARIOS[candidate]
        return None

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="mock",
            model=None,
            configured=True,
            cache_mode=self.settings.resolved_cache_mode(),
            provenance_label=Provenance.MOCK,
            detail=(
                "Scripted offline responses. Results are labelled MOCK and are not "
                f"model output. {len(self.registry)} sample video(s) registered."
            ),
        )

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        return None

    # -- provider interface ------------------------------------------------

    async def describe_expert_window(self, request: WindowRequest) -> WindowDescription:
        from app.services.video import evidence_for_window

        scenario = self.resolve(request.video)
        evidence = evidence_for_window(request.video, request.window)
        if scenario is None or scenario.kind != "expert":
            raise ProviderError(UNSCRIPTED_MESSAGE)

        middle = (request.window.t_start + request.window.t_end) / 2
        chosen = None
        for window in scenario.windows:
            if window.t_from <= middle < window.t_to:
                chosen = window
                break
        if chosen is None:
            chosen = scenario.windows[-1]

        return WindowDescription(
            window_id=request.window.window_id,
            t_start=request.window.t_start,
            t_end=request.window.t_end,
            objects=list(chosen.objects),
            actions=list(chosen.actions),
            changes=list(chosen.changes),
            candidate_steps=list(chosen.candidate_steps),
            limitations=list(chosen.limitations),
            evidence=evidence,
            provenance=Provenance.MOCK,
        )

    async def propose_graph(self, request: ProposalRequest) -> GraphProposal:
        scenario = self.resolve(request.video)
        if scenario is None or scenario.kind != "expert":
            raise ProviderError(UNSCRIPTED_MESSAGE)
        proposal = GraphProposal.model_validate(PROPOSAL)
        # Attach evidence from the expert windows that suggested each step.
        steps = []
        for index, step in enumerate(proposal.steps):
            evidence = []
            if index < len(request.descriptions):
                match = request.descriptions[
                    min(index * max(1, len(request.descriptions) // max(1, len(proposal.steps))), len(request.descriptions) - 1)
                ]
                evidence = [match.evidence]
            steps.append(step.model_copy(update={"evidence": evidence}))
        return proposal.model_copy(update={"steps": steps})

    async def observe_learner_window(
        self, request: ObserveRequest
    ) -> list[Observation]:
        from app.services.video import locate_evidence

        scenario = self.resolve(request.video)
        if scenario is None or scenario.kind != "attempt":
            raise ProviderError(UNSCRIPTED_MESSAGE)

        mapping = map_step_ids(
            [event.step_id for event in scenario.events], request.steps
        )
        observations: list[Observation] = []
        for index, event in enumerate(scenario.events):
            if not (request.window.t_start <= event.t < request.window.t_end):
                continue
            step_id = mapping.get(event.step_id)
            if step_id is None:
                continue
            observations.append(
                Observation(
                    observation_id=f"{request.window.window_id}_{event.step_id}_{index}",
                    window_id=request.window.window_id,
                    step_id=step_id,
                    status=ObservationStatus(event.status),
                    confidence=event.confidence,
                    t_start=event.t,
                    t_end=min(event.t + 1.5, request.window.t_end),
                    evidence=locate_evidence(
                        request.video,
                        event.t,
                        min(event.t + 1.5, request.window.t_end),
                        note=event.rationale,
                    ),
                    rationale=event.rationale,
                    provenance=Provenance.MOCK,
                )
            )
        return observations

    def scenario_limitations(self, video: VideoMeta) -> list[str]:
        scenario = self.resolve(video)
        return list(scenario.limitations) if scenario else []
