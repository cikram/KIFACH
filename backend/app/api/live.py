"""Live camera mode over a WebSocket.

The browser sends timestamped JPEG frames; the server groups them into the same
windows the upload path uses, runs the same observation and engine code, and
pushes engine events back. Upload remains the reliable path: live mode adds the
demo's immediacy but inherits every provider latency and camera problem.

Live frames are saved under the media root so the attempt keeps replayable
evidence. The browser also uploads its MediaRecorder capture at the end and
attaches it to the attempt, which lets evidence clicks seek real video; live
frame times are measured from the start of that recording so the two clocks
agree.
"""

from __future__ import annotations

import base64
import binascii
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import settings_dep, store_dep
from app.config import Settings
from app.domain.models import (
    Attempt,
    AttemptStatus,
    Frame,
    Observation,
    SkillStatus,
    VideoMeta,
    Window,
)
from app.providers import ObserveRequest, ProviderError, build_provider, provider_label
from app.services.observation_extractor import apply_engine, engine_config, normalize
from app.services.storage import NotFound, Store, is_safe_id, new_id
from app.services.video import sha256_bytes

log = logging.getLogger("kifach.live")
router = APIRouter(tags=["live"])

MAX_FRAME_BYTES = 2 * 1024 * 1024


def _live_video(settings: Settings, session_id: str, scenario: str | None) -> VideoMeta:
    return VideoMeta(
        video_id=session_id,
        filename=f"{session_id}.webm",
        content_type="video/webm",
        size_bytes=0,
        duration_s=0.0,
        fps_source=0.0,
        width=0,
        height=0,
        sha256="0" * 64,
        path=f"{session_id}/session.webm",
        sample_fps=settings.sample_fps,
        scenario_hint=scenario,
    )


@router.websocket("/live/{skill_id}")
async def live(
    websocket: WebSocket,
    skill_id: str,
    settings: Settings = Depends(settings_dep),
    store: Store = Depends(store_dep),
) -> None:
    await websocket.accept()
    scenario = websocket.query_params.get("scenario")

    if not is_safe_id(skill_id):
        await websocket.send_json(
            {"type": "error", "code": "invalid_id", "message": "Invalid skill id."}
        )
        await websocket.close()
        return
    try:
        skill = store.get_skill(skill_id)
    except NotFound:
        await websocket.send_json(
            {
                "type": "error",
                "code": "not_found",
                "message": f"No skill with id {skill_id}.",
            }
        )
        await websocket.close()
        return
    if skill.status is not SkillStatus.PUBLISHED:
        await websocket.send_json(
            {
                "type": "error",
                "code": "skill_not_published",
                "message": f"{skill.title} is still a draft. Publish it first.",
            }
        )
        await websocket.close()
        return

    session_id = new_id("live")
    video = _live_video(settings, session_id, scenario)
    frames_dir = settings.media_root / session_id / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    attempt = Attempt(
        attempt_id=new_id("att"),
        skill_id=skill_id,
        live_session_id=session_id,
        mode="live",
        config=engine_config(settings, "live"),
        created_at=datetime.now(timezone.utc),
    )
    store.save_attempt(attempt)

    provider = build_provider(settings)
    label = provider_label(settings)
    await websocket.send_json(
        {
            "type": "session_started",
            "attempt_id": attempt.attempt_id,
            "live_session_id": session_id,
            "provider_label": label,
            "window_seconds": settings.window_seconds,
            "confirmations_required": attempt.config.required_confirmations(),
            "steps": [
                {"step_id": s.step_id, "title": s.title, "checkpoint": s.checkpoint}
                for s in skill.steps
            ],
        }
    )

    pending: list[Frame] = []
    observations: list[Observation] = []
    limitations: list[str] = []
    window_index = 0
    window_start = 0.0
    emitted = 0
    current = attempt

    async def close_window(end_t: float) -> None:
        nonlocal pending, window_index, window_start, observations, emitted, current
        if not pending:
            window_start = end_t
            return
        window_index += 1
        window = Window(
            window_id=f"lw{window_index:03d}",
            t_start=round(window_start, 3),
            t_end=round(max(end_t, window_start + 0.01), 3),
            frame_indexes=[f.index for f in pending],
        )
        snapshot = video.model_copy(update={"frames": list(video.frames)})
        try:
            found = await provider.observe_learner_window(
                ObserveRequest(
                    video=snapshot,
                    window=window,
                    frames=pending[: settings.max_images_per_call],
                    steps=skill.steps,
                    skill_title=skill.title,
                    checkpoints={s.step_id: s.checkpoint for s in skill.steps},
                )
            )
        except ProviderError as exc:
            message = (
                f"The window {window.t_start:.1f}s-{window.t_end:.1f}s could not be "
                f"analysed: {exc}"
            )
            limitations.append(message)
            await websocket.send_json(
                {"type": "window_error", "window_id": window.window_id, "message": message}
            )
            found = []

        observations.extend(found)
        current = apply_engine(current, skill, normalize(observations))
        for event in current.events[emitted:]:
            await websocket.send_json(
                {"type": "engine_event", "event": event.model_dump(mode="json")}
            )
        emitted = len(current.events)
        await websocket.send_json(
            {
                "type": "state_updated",
                "window_id": window.window_id,
                "observations": [o.model_dump(mode="json") for o in found],
                "step_states": {k: v.value for k, v in current.step_states.items()},
                "alerts": [a.model_dump(mode="json") for a in current.alerts],
                "verdict": current.verdict.value,
            }
        )
        store.save_attempt(
            current.model_copy(
                update={"limitations": list(limitations), "observations": normalize(observations)}
            )
        )
        pending = []
        window_start = max(end_t - settings.window_overlap, 0.0)

    try:
        while True:
            message = await websocket.receive_json()
            kind = str(message.get("type", ""))

            if kind == "frame":
                try:
                    timestamp = float(message.get("t", 0.0))
                except (TypeError, ValueError):
                    continue
                raw = message.get("jpeg_base64") or ""
                try:
                    payload = base64.b64decode(raw, validate=True)
                except (binascii.Error, ValueError):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "bad_frame",
                            "message": "A frame was not valid base64 JPEG data.",
                        }
                    )
                    continue
                if not payload or len(payload) > MAX_FRAME_BYTES:
                    continue
                index = len(video.frames)
                name = f"f{index:05d}_{int(round(timestamp * 1000)):08d}.jpg"
                (frames_dir / name).write_bytes(payload)
                frame = Frame(
                    index=index,
                    timestamp_s=round(max(timestamp, 0.0), 3),
                    media_path=f"{session_id}/frames/{name}",
                    sha256=sha256_bytes(payload),
                )
                video = video.model_copy(update={"frames": [*video.frames, frame]})
                pending.append(frame)
                if frame.timestamp_s - window_start >= settings.window_seconds:
                    await close_window(frame.timestamp_s)

            elif kind == "stop":
                last = video.frames[-1].timestamp_s if video.frames else 0.0
                await close_window(last)
                final = current.model_copy(
                    update={
                        "status": AttemptStatus.COMPLETE,
                        "observations": normalize(observations),
                        "limitations": list(limitations),
                    }
                )
                final = apply_engine(final, skill, normalize(observations))
                final = final.model_copy(update={"status": AttemptStatus.COMPLETE})
                video_final = video.model_copy(
                    update={"duration_s": video.frames[-1].timestamp_s if video.frames else 0.0}
                )
                store.save_video(video_final)
                store.save_attempt(final)
                await websocket.send_json(
                    {
                        "type": "session_complete",
                        "attempt_id": final.attempt_id,
                        "verdict": final.verdict.value,
                        "provider_label": label,
                    }
                )
                break

            elif kind == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        log.info("Live session %s disconnected", session_id)
        if video.frames:
            store.save_video(video)
        store.save_attempt(
            current.model_copy(
                update={
                    "status": AttemptStatus.COMPLETE,
                    "observations": normalize(observations),
                    "limitations": [
                        *limitations,
                        "The live session ended before the learner stopped it.",
                    ],
                }
            )
        )
    finally:
        await provider.aclose()
