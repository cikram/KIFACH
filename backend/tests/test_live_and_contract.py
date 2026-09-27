"""The live WebSocket protocol, pipeline behaviour, and the frontend contract."""

from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.domain.models import (
    EvidenceRef,
    Observation,
    ObservationStatus,
    Provenance,
)
from app.services.observation_extractor import normalize, observation_summary
from tests.conftest import REPO_ROOT, sample_path
from tests.test_api import publish_reference_skill, upload, wait_for_job


def jpeg_frame(label: str) -> str:
    image = np.full((180, 320, 3), 40, dtype=np.uint8)
    cv2.putText(image, label, (12, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240, 240, 240), 2)
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def test_live_session_runs_the_same_engine_path(client):
    """A scripted live session produces engine events and a saved attempt."""
    skill_id = publish_reference_skill(client)

    with client.websocket_connect(
        f"/api/live/{skill_id}?scenario=correct"
    ) as socket:
        started = socket.receive_json()
        assert started["type"] == "session_started"
        assert started["provider_label"] == "MOCK"
        assert started["confirmations_required"] >= 2, "live mode is stricter"
        attempt_id = started["attempt_id"]

        payload = jpeg_frame("live")
        for step in range(28):
            socket.send_json(
                {"type": "frame", "t": step * 0.5, "jpeg_base64": payload}
            )
        socket.send_json({"type": "ping"})
        socket.send_json({"type": "stop"})

        messages = []
        while True:
            message = socket.receive_json()
            messages.append(message)
            if message["type"] == "session_complete":
                break

    kinds = {message["type"] for message in messages}
    assert "state_updated" in kinds
    assert {"engine_event", "window_error"} & kinds

    detail = client.get(f"/api/attempts/{attempt_id}").json()
    assert detail["attempt"]["mode"] == "live"
    assert detail["attempt"]["live_session_id"]
    assert detail["attempt"]["config"]["mode"] == "live"


def test_live_rejects_a_draft_skill(client):
    video = upload(client)
    accepted = client.post("/api/skills/teach", json={"video_id": video["video_id"]})
    state = wait_for_job(client, accepted.json()["job_id"])
    skill_id = state["result"]["skill_id"]

    with client.websocket_connect(f"/api/live/{skill_id}") as socket:
        message = socket.receive_json()
    assert message["type"] == "error"
    assert message["code"] == "skill_not_published"


def test_live_rejects_an_unknown_skill(client):
    with client.websocket_connect("/api/live/skill_missing") as socket:
        message = socket.receive_json()
    assert message["type"] == "error"
    assert message["code"] == "not_found"


def test_live_rejects_a_malformed_frame(client):
    skill_id = publish_reference_skill(client)
    with client.websocket_connect(f"/api/live/{skill_id}?scenario=correct") as socket:
        socket.receive_json()
        socket.send_json({"type": "frame", "t": 0.5, "jpeg_base64": "not base64!!"})
        message = socket.receive_json()
    assert message["type"] == "error"
    assert message["code"] == "bad_frame"


def test_attaching_a_recording_to_an_attempt(client):
    skill_id = publish_reference_skill(client)
    with client.websocket_connect(f"/api/live/{skill_id}?scenario=correct") as socket:
        started = socket.receive_json()
        socket.send_json({"type": "stop"})
        socket.receive_json()
    attempt_id = started["attempt_id"]

    recording = upload(client, "correct.webm")
    updated = client.post(
        f"/api/attempts/{attempt_id}/media", json={"video_id": recording["video_id"]}
    ).json()
    assert updated["media_id"] == recording["video_id"]

    missing = client.post(
        f"/api/attempts/{attempt_id}/media", json={"video_id": "vid_missing"}
    )
    assert missing.status_code == 404


# --- pipeline helpers ----------------------------------------------------


def observation(step: str, t: float, status=ObservationStatus.COMPLETED, confidence=0.9):
    return Observation(
        observation_id=f"{step}-{t}",
        window_id=f"w{int(t)}",
        step_id=step,
        status=status,
        confidence=confidence,
        t_start=t,
        t_end=t + 1,
        evidence=EvidenceRef(video_id="v", t_start=t, t_end=t + 1),
        provenance=Provenance.MOCK,
    )


def test_normalize_collapses_one_event_seen_by_two_windows():
    collapsed = normalize(
        [
            observation("a", 5.0, confidence=0.7),
            observation("a", 5.1, confidence=0.85),
            observation("a", 12.0),
        ]
    )
    assert len(collapsed) == 2
    assert collapsed[0].confidence == 0.85, "the more confident report survives"


def test_normalize_keeps_different_statuses_of_one_step():
    kept = normalize(
        [
            observation("a", 5.0, status=ObservationStatus.ABSENT),
            observation("a", 5.0, status=ObservationStatus.COMPLETED),
        ]
    )
    assert len(kept) == 2


def test_normalize_orders_by_source_time():
    ordered = normalize([observation("b", 9.0), observation("a", 2.0)])
    assert [item.t_start for item in ordered] == [2.0, 9.0]


def test_observation_summary_counts_every_status():
    counts = observation_summary(
        [observation("a", 1.0), observation("b", 2.0, status=ObservationStatus.ABSENT)]
    )
    assert counts["completed"] == 1
    assert counts["absent"] == 1
    assert counts["uncertain"] == 0


# --- contract ------------------------------------------------------------


def test_frontend_types_match_the_backend_models():
    """`python scripts/gen_types.py` must have been run after a model change."""
    script = REPO_ROOT / "scripts" / "gen_types.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sample_registry_matches_the_generated_fixtures():
    """The mock keys its scripted answers on these hashes, so they must agree."""
    import hashlib
    import json

    registry_path = REPO_ROOT / "samples" / "scenarios.json"
    if not registry_path.exists():
        pytest.skip("Run python scripts/make_synthetic_video.py first")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for entry in registry["videos"].values():
        path = sample_path(entry["file"])
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"{entry['file']} does not match the registry"
