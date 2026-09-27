"""Background jobs with a replayable event stream.

A job keeps its whole event list in memory and on disk. SSE clients get every
event from a given id onwards, so a page refresh in the middle of a teach run
recovers the progress it missed instead of hanging on an empty stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable

from app.config import Settings, get_settings
from app.services.storage import new_id, write_json_atomic

log = logging.getLogger("kifach.jobs")


@dataclass
class JobEvent:
    id: int
    type: str
    data: dict[str, Any]
    at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "at": self.at, "data": self.data}


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "running"
    events: list[JobEvent] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    subscribers: list[asyncio.Queue[JobEvent]] = field(default_factory=list)
    task: asyncio.Task[None] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "events": [event.as_dict() for event in self.events],
        }


class JobManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.jobs: dict[str, Job] = {}

    # -- lifecycle ---------------------------------------------------------

    def create(self, kind: str) -> Job:
        job = Job(job_id=new_id("job"), kind=kind)
        self.jobs[job.job_id] = job
        self._persist(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def _persist(self, job: Job) -> None:
        path = self.settings.data_root / "jobs" / f"{job.job_id}.json"
        try:
            write_json_atomic(path, job.as_dict())
        except OSError as exc:  # pragma: no cover - disk problems only
            log.warning("Could not persist job %s: %s", job.job_id, exc)

    def emit(self, job: Job, event_type: str, **data: Any) -> JobEvent:
        event = JobEvent(id=len(job.events) + 1, type=event_type, data=data)
        job.events.append(event)
        for queue in list(job.subscribers):
            queue.put_nowait(event)
        self._persist(job)
        return event

    def finish(self, job: Job, **result: Any) -> None:
        job.status = "complete"
        job.result = result
        self.emit(job, "complete", **result)

    def fail(self, job: Job, code: str, message: str) -> None:
        job.status = "failed"
        job.error = message
        self.emit(job, "error", code=code, message=message)

    async def run(
        self, job: Job, coroutine: Callable[[Job], Awaitable[None]]
    ) -> None:
        async def wrapper() -> None:
            try:
                await coroutine(job)
            except asyncio.CancelledError:  # pragma: no cover - shutdown path
                raise
            except Exception as exc:  # noqa: BLE001 - surfaced to the client
                log.exception("Job %s failed", job.job_id)
                self.fail(job, "job_failed", str(exc) or exc.__class__.__name__)

        job.task = asyncio.create_task(wrapper())

    # -- streaming ---------------------------------------------------------

    async def stream(self, job: Job, last_event_id: int = 0) -> AsyncIterator[JobEvent]:
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        job.subscribers.append(queue)
        try:
            for event in list(job.events):
                if event.id > last_event_id:
                    yield event
            while job.status == "running":
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield JobEvent(id=0, type="ping", data={})
                    continue
                yield event
            # Drain anything that arrived while the job was finishing.
            while not queue.empty():
                yield queue.get_nowait()
        finally:
            with contextlib.suppress(ValueError):
                job.subscribers.remove(queue)


_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager


def reset_job_manager() -> None:
    """Used by tests to isolate job state."""
    global _manager
    _manager = None
