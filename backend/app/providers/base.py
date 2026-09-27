"""The provider interface every perception backend implements.

A provider answers three questions and nothing more: what is visible in an
expert window, what procedure the expert footage suggests, and what is visible
in a learner window. It never decides whether an attempt passed — that is the
deterministic engine's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.models import (
    Frame,
    GraphProposal,
    Observation,
    ProviderHealth,
    Step,
    VideoMeta,
    Window,
    WindowDescription,
)


class ProviderError(RuntimeError):
    """A provider could not answer. The caller degrades to an uncertain result."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class CacheMiss(ProviderError):
    """Replay mode was asked for something that was never cached."""

    def __init__(self, message: str = "No cached model response for this window.") -> None:
        super().__init__(message)


@dataclass
class WindowRequest:
    video: VideoMeta
    window: Window
    frames: list[Frame]
    task_hint: str = ""


@dataclass
class ProposalRequest:
    video: VideoMeta
    descriptions: list[WindowDescription]
    key_frames: list[Frame]
    task_hint: str = ""


@dataclass
class ObserveRequest:
    video: VideoMeta
    window: Window
    frames: list[Frame]
    steps: list[Step]
    skill_title: str = ""
    checkpoints: dict[str, str] = field(default_factory=dict)


class VisionProvider(Protocol):
    name: str

    async def describe_expert_window(
        self, request: WindowRequest
    ) -> WindowDescription: ...

    async def propose_graph(self, request: ProposalRequest) -> GraphProposal: ...

    async def observe_learner_window(
        self, request: ObserveRequest
    ) -> list[Observation]: ...

    def health(self) -> ProviderHealth: ...

    async def aclose(self) -> None: ...
