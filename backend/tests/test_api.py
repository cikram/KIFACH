"""HTTP surface: success and failure for every documented endpoint."""

from __future__ import annotations

import io
import time

import pytest

from tests.conftest import sample_path


def upload(client, name: str = "expert.webm"):
    with open(sample_path(name), "rb") as handle:
        response = client.post(
            "/api/videos", files={"file": (name, handle, "video/webm")}
        )
    assert response.status_code == 200, response.text
    return response.json()


def wait_for_job(client, job_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job_id}").json()
        if state["status"] != "running":
            return state
        time.sleep(0.1)
    raise AssertionError(f"Job {job_id} never finished")


def publish_reference_skill(client) -> str:
    video = upload(client)
    accepted = client.post(
        "/api/skills/teach", json={"video_id": video["video_id"]}
    ).json()
    state = wait_for_job(client, accepted["job_id"])
    assert state["status"] == "complete", state
    skill_id = state["result"]["skill_id"]

    draft = client.get(f"/api/skills/{skill_id}").json()
    client.put(
        f"/api/skills/{skill_id}",
        json={
            "confirmed_rule_ids": [rule["rule_id"] for rule in draft["rules"]],
            "mark_reviewed": True,
        },
    )
    published = client.post(f"/api/skills/{skill_id}/publish").json()
    assert published["validation"]["ok"], published
    return skill_id


def test_health_reports_provider_without_calling_it(client):
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["provider"]["provider"] == "mock"
    assert payload["provider"]["provenance_label"] == "MOCK"


def test_provider_check_is_explicit(client):
    payload = client.post("/api/health/provider-check").json()
    assert payload["provider"] == "mock"
    assert payload["reachable"] is True


def test_upload_accepts_video_and_records_metadata(client):
    payload = upload(client)
    assert payload["duration_s"] > 0
    assert payload["sha256"]
    assert payload["path"].endswith(".webm")


def test_upload_rejects_a_non_video_extension(client):
    response = client.post(
        "/api/videos", files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_media"


def test_upload_rejects_a_corrupt_video(client):
    response = client.post(
        "/api/videos",
        files={"file": ("broken.mp4", io.BytesIO(b"not a real video"), "video/mp4")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] in ("unreadable_media", "unsupported_media")


def test_teach_rejects_an_unknown_video(client):
    response = client.post("/api/skills/teach", json={"video_id": "vid_missing"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_teach_rejects_an_unsafe_id(client):
    response = client.post("/api/skills/teach", json={"video_id": "../etc/passwd"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_id"


def test_teach_produces_a_reviewable_draft(client):
    video = upload(client)
    accepted = client.post(
        "/api/skills/teach",
        json={"video_id": video["video_id"], "task_hint": "light an LED"},
    )
    assert accepted.status_code == 202
    state = wait_for_job(client, accepted.json()["job_id"])
    assert state["status"] == "complete", state

    kinds = [event["type"] for event in state["events"]]
    assert "extraction_complete" in kinds
    assert "window_analysed" in kinds
    assert "validation_complete" in kinds

    skill = client.get(f"/api/skills/{state['result']['skill_id']}").json()
    assert skill["status"] == "draft"
    assert 3 <= len(skill["steps"]) <= 8
    assert skill["rules"], "the reference task has a safety rule to review"
    assert all(rule["proposed_by_model"] for rule in skill["rules"])
    assert not any(rule["confirmed_by_expert"] for rule in skill["rules"])


def test_publishing_requires_confirming_every_proposed_rule(client):
    video = upload(client)
    accepted = client.post("/api/skills/teach", json={"video_id": video["video_id"]})
    state = wait_for_job(client, accepted.json()["job_id"])
    skill_id = state["result"]["skill_id"]

    refused = client.post(f"/api/skills/{skill_id}/publish").json()
    assert refused["skill"] is None
    assert not refused["validation"]["ok"]
    assert any(
        issue["code"] == "rules_unconfirmed" for issue in refused["validation"]["issues"]
    )

    draft = client.get(f"/api/skills/{skill_id}").json()
    client.put(
        f"/api/skills/{skill_id}",
        json={
            "confirmed_rule_ids": [rule["rule_id"] for rule in draft["rules"]],
            "mark_reviewed": True,
        },
    )
    accepted_publish = client.post(f"/api/skills/{skill_id}/publish").json()
    assert accepted_publish["validation"]["ok"]
    assert accepted_publish["skill"]["status"] == "published"
    assert accepted_publish["skill"]["review"]["reviewed"] is True


def test_a_published_skill_cannot_be_edited(client):
    skill_id = publish_reference_skill(client)
    response = client.put(f"/api/skills/{skill_id}", json={"title": "Renamed"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_published"


def test_editing_a_step_clears_its_proposed_flag(client):
    video = upload(client)
    accepted = client.post("/api/skills/teach", json={"video_id": video["video_id"]})
    state = wait_for_job(client, accepted.json()["job_id"])
    skill_id = state["result"]["skill_id"]
    draft = client.get(f"/api/skills/{skill_id}").json()

    steps = draft["steps"]
    steps[0]["title"] = "Seat the LED firmly"
    updated = client.put(f"/api/skills/{skill_id}", json={"steps": steps}).json()
    assert updated["steps"][0]["proposed_by_model"] is False
    assert updated["steps"][0]["step_id"] in updated["review"]["edited_steps"]
    assert updated["steps"][1]["proposed_by_model"] is True


def test_a_cyclic_edit_is_reported_before_publishing(client):
    video = upload(client)
    accepted = client.post("/api/skills/teach", json={"video_id": video["video_id"]})
    state = wait_for_job(client, accepted.json()["job_id"])
    skill_id = state["result"]["skill_id"]
    draft = client.get(f"/api/skills/{skill_id}").json()

    steps = draft["steps"]
    steps[0]["depends_on"] = [steps[1]["step_id"]]
    steps[1]["depends_on"] = [steps[0]["step_id"]]
    client.put(f"/api/skills/{skill_id}", json={"steps": steps})

    validation = client.get(f"/api/skills/{skill_id}/validation").json()
    assert not validation["ok"]
    assert any(issue["code"] == "cycle" for issue in validation["issues"])

    refused = client.post(f"/api/skills/{skill_id}/publish").json()
    assert refused["skill"] is None


def test_attempt_against_an_unpublished_skill_is_refused(client):
    video = upload(client)
    accepted = client.post("/api/skills/teach", json={"video_id": video["video_id"]})
    state = wait_for_job(client, accepted.json()["job_id"])
    skill_id = state["result"]["skill_id"]

    attempt_video = upload(client, "correct.webm")
    response = client.post(
        f"/api/skills/{skill_id}/attempts",
        json={"video_id": attempt_video["video_id"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "skill_not_published"


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        ("correct.webm", "VERIFIED"),
        ("wrong_order.webm", "NOT_VERIFIED"),
        ("uncertain.webm", "INCONCLUSIVE"),
        ("corrected.webm", "VERIFIED"),
        ("alternate_order.webm", "VERIFIED"),
    ],
)
def test_each_scenario_reaches_its_expected_verdict(client, sample, expected):
    skill_id = publish_reference_skill(client)
    video = upload(client, sample)
    accepted = client.post(
        f"/api/skills/{skill_id}/attempts", json={"video_id": video["video_id"]}
    )
    assert accepted.status_code == 202
    state = wait_for_job(client, accepted.json()["job_id"])
    assert state["status"] == "complete", state
    assert state["result"]["verdict"] == expected

    detail = client.get(f"/api/attempts/{state['result']['attempt_id']}").json()
    assert detail["attempt"]["verdict"] == expected
    assert detail["attempt"]["observations"], "an assessment needs observations"
    for observation in detail["attempt"]["observations"]:
        assert observation["evidence"]["video_id"] == video["video_id"]
        assert observation["provenance"] == "MOCK"


def test_replay_reproduces_a_stored_attempt(client):
    skill_id = publish_reference_skill(client)
    video = upload(client, "wrong_order.webm")
    accepted = client.post(
        f"/api/skills/{skill_id}/attempts", json={"video_id": video["video_id"]}
    )
    state = wait_for_job(client, accepted.json()["job_id"])
    attempt_id = state["result"]["attempt_id"]

    replayed = client.post(f"/api/attempts/{attempt_id}/replay").json()
    assert replayed["identical"] is True
    assert replayed["differences"] == []
    assert replayed["verdict"] == replayed["previous_verdict"]


def test_unknown_attempt_and_skill_return_the_error_shape(client):
    for path in ("/api/attempts/att_missing", "/api/skills/skill_missing"):
        response = client.get(path)
        assert response.status_code == 404
        body = response.json()
        assert set(body["error"]) == {"code", "message"}


def test_media_is_served_and_traversal_is_refused(client):
    video = upload(client)
    accepted = client.post("/api/skills/teach", json={"video_id": video["video_id"]})
    wait_for_job(client, accepted.json()["job_id"])
    meta = client.get(f"/api/videos/{video['video_id']}").json()

    frame = meta["frames"][0]["media_path"]
    served = client.get(f"/api/media/{frame}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"

    # A traversal must never serve a repository file. Some of these are
    # normalized away by the HTTP client before they reach the route, which is
    # why safe_media_path is also unit tested directly.
    for attack in (
        "../../AGENTS.md",
        "..%2f..%2fAGENTS.md",
        "....//AGENTS.md",
        "%2e%2e/%2e%2e/AGENTS.md",
        "/etc/passwd",
    ):
        response = client.get(f"/api/media/{attack}")
        assert b"KIFACH project guidance" not in response.content, attack
        assert b"root:" not in response.content, attack
        if response.status_code == 200:
            # Only the SPA fallback may answer, and only with the app shell.
            assert b"<div id=\"root\">" in response.content, attack


def test_deleting_a_skill_removes_it_from_the_library(client):
    skill_id = publish_reference_skill(client)
    assert client.delete(f"/api/skills/{skill_id}").status_code == 204
    assert client.get(f"/api/skills/{skill_id}").status_code == 404
    assert all(item["skill_id"] != skill_id for item in client.get("/api/skills").json())


def test_skill_list_summarizes_the_latest_attempt(client):
    skill_id = publish_reference_skill(client)
    video = upload(client, "correct.webm")
    accepted = client.post(
        f"/api/skills/{skill_id}/attempts", json={"video_id": video["video_id"]}
    )
    wait_for_job(client, accepted.json()["job_id"])

    summary = next(
        item for item in client.get("/api/skills").json() if item["skill_id"] == skill_id
    )
    assert summary["status"] == "published"
    assert summary["last_verdict"] == "VERIFIED"
    assert summary["step_count"] >= 3


def test_job_events_stream_replays_from_the_beginning(client):
    video = upload(client)
    accepted = client.post("/api/skills/teach", json={"video_id": video["video_id"]})
    job_id = accepted.json()["job_id"]
    wait_for_job(client, job_id)

    with client.stream(
        "GET", f"/api/jobs/{job_id}/events?last_event_id=0"
    ) as response:
        assert response.status_code == 200
        body = ""
        for chunk in response.iter_text():
            body += chunk
            if "complete" in body:
                break
    assert "extraction_complete" in body


def test_unknown_job_is_not_found(client):
    assert client.get("/api/jobs/job_missing").status_code == 404
    assert client.get("/api/jobs/job_missing/events").status_code == 404
