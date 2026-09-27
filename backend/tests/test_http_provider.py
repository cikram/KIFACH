"""The real provider's mechanics, exercised offline with a stub transport.

No credentials are needed and no packet leaves the machine: httpx.MockTransport
answers as an OpenAI-compatible endpoint would. These tests cover the parts that
are easy to get wrong and hard to debug during a demo — retries, JSON repair,
image-count reduction, and what is written to the cache.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.config import get_settings, reset_settings_cache
from app.domain.models import Provenance
from app.providers.base import ObserveRequest, ProposalRequest, ProviderError, WindowRequest
from app.providers.http_vlm import HttpVlmProvider
from app.services.storage import Store
from app.services.video import extract_frames, store_upload
from tests.conftest import sample_path


def chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"total_tokens": 42},
        },
        headers={"x-request-id": "req-1"},
    )


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("KIFACH_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("KIFACH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KIFACH_CACHE", "on")
    monkeypatch.setenv("KIFACH_MAX_RETRIES", "3")
    reset_settings_cache()
    resolved = get_settings()
    resolved.ensure_dirs()
    yield resolved
    reset_settings_cache()


@pytest.fixture
def prepared(settings):
    """A stored, extracted video plus its first window."""
    store = Store(settings)
    video = store_upload(
        sample_path("expert.webm"), "expert.webm", "video/webm", settings, store
    )
    extraction = extract_frames(video, settings, store)
    return extraction


def no_backoff(monkeypatch) -> None:
    """Keep the retry logic, drop the waiting."""
    real_sleep = asyncio.sleep

    async def instant(_delay: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr("app.providers.http_vlm.asyncio.sleep", instant)


def build(settings, handler) -> HttpVlmProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, headers={"Authorization": "Bearer x"})
    return HttpVlmProvider(
        settings,
        name="nvidia",
        base_url="https://example.invalid/v1",
        api_key="test-key",
        model="nvidia/cosmos-reason2-8b",
        client=client,
    )


def test_a_window_description_is_parsed_and_labelled_live(settings, prepared):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return chat_response(
            json.dumps(
                {
                    "objects": ["breadboard", "red LED"],
                    "actions": ["a hand seats the LED"],
                    "changes": ["the LED is now in the board"],
                    "candidate_steps": ["Seat the LED"],
                    "limitations": ["a hand covers the left rail"],
                }
            )
        )

    provider = build(settings, handler)
    description = asyncio.run(
        provider.describe_expert_window(
            WindowRequest(
                video=prepared.video,
                window=prepared.windows[0],
                frames=prepared.video.frames[:3],
            )
        )
    )
    assert description.provenance is Provenance.LIVE
    assert description.objects == ["breadboard", "red LED"]
    assert description.limitations
    assert description.evidence.video_id == prepared.video.video_id

    body = json.loads(calls[0].content)
    assert body["model"] == "nvidia/cosmos-reason2-8b"
    assert body["temperature"] == 0.0
    images = [
        part
        for part in body["messages"][1]["content"]
        if part.get("type") == "image_url"
    ]
    assert images, "frames must be sent as image_url parts"
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    asyncio.run(provider.aclose())


def test_a_fenced_answer_is_still_parsed(settings, prepared):
    def handler(_: httpx.Request) -> httpx.Response:
        return chat_response('```json\n{"objects": ["led"]}\n```')

    provider = build(settings, handler)
    description = asyncio.run(
        provider.describe_expert_window(
            WindowRequest(
                video=prepared.video,
                window=prepared.windows[0],
                frames=prepared.video.frames[:1],
            )
        )
    )
    assert description.objects == ["led"]
    asyncio.run(provider.aclose())


def test_invalid_json_triggers_one_repair_request(settings, prepared):
    attempts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        attempts.append(body)
        if len(attempts) == 1:
            return chat_response("I think I saw a breadboard.")
        return chat_response('{"objects": ["breadboard"]}')

    provider = build(settings, handler)
    description = asyncio.run(
        provider.describe_expert_window(
            WindowRequest(
                video=prepared.video,
                window=prepared.windows[0],
                frames=prepared.video.frames[:1],
            )
        )
    )
    assert description.objects == ["breadboard"]
    assert len(attempts) == 2
    assert "did not match the required JSON shape" in json.dumps(attempts[1])
    asyncio.run(provider.aclose())


def test_a_rate_limit_is_retried_then_succeeds(settings, prepared, monkeypatch):
    no_backoff(monkeypatch)
    statuses = [429, 503, 200]

    def handler(_: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        if status == 200:
            return chat_response('{"objects": ["led"]}')
        return httpx.Response(status, json={"error": "slow down"})

    provider = build(settings, handler)
    description = asyncio.run(
        provider.describe_expert_window(
            WindowRequest(
                video=prepared.video,
                window=prepared.windows[0],
                frames=prepared.video.frames[:1],
            )
        )
    )
    assert description.objects == ["led"]
    assert statuses == []
    asyncio.run(provider.aclose())


def test_persistent_failure_raises_a_reportable_error(settings, prepared, monkeypatch):
    no_backoff(monkeypatch)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = build(settings, handler)
    with pytest.raises(ProviderError) as problem:
        asyncio.run(
            provider.describe_expert_window(
                WindowRequest(
                    video=prepared.video,
                    window=prepared.windows[0],
                    frames=prepared.video.frames[:1],
                )
            )
        )
    assert "did not answer" in str(problem.value)
    asyncio.run(provider.aclose())


def test_a_rejected_payload_reduces_the_image_count(settings, prepared):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(413, json={"error": "too many images"})

    provider = build(settings, handler)
    before = provider.images_per_call
    with pytest.raises(ProviderError):
        asyncio.run(
            provider.describe_expert_window(
                WindowRequest(
                    video=prepared.video,
                    window=prepared.windows[0],
                    frames=prepared.video.frames[:4],
                )
            )
        )
    assert provider.images_per_call < before
    assert any("reduced images per call" in note for note in provider.notes)
    asyncio.run(provider.aclose())


def test_a_second_identical_request_is_served_from_cache(settings, prepared):
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return chat_response('{"objects": ["led"]}')

    request = WindowRequest(
        video=prepared.video,
        window=prepared.windows[0],
        frames=prepared.video.frames[:2],
    )
    provider = build(settings, handler)
    asyncio.run(provider.describe_expert_window(request))
    asyncio.run(provider.describe_expert_window(request))
    assert calls["count"] == 1, "the second call must come from the cache"

    cached = list(settings.cache_root.glob("*.json"))
    assert cached
    entry = json.loads(cached[0].read_text(encoding="utf-8"))
    assert entry["origin"] == "live_model_response"
    assert entry["provider"] == "nvidia"
    asyncio.run(provider.aclose())


def test_learner_observations_are_validated_and_filtered(settings, prepared):
    from app.domain.models import Step

    steps = [
        Step(step_id="led", title="Seat the LED", checkpoint="LED seated"),
        Step(step_id="resistor", title="Add the resistor", checkpoint="resistor in"),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return chat_response(
            json.dumps(
                {
                    "observations": [
                        {
                            "step_id": "led",
                            "status": "completed",
                            "confidence": 0.88,
                            "rationale": "the LED is in two rows",
                        },
                        {
                            "step_id": "resistor",
                            "status": "nonsense",
                            "confidence": 5,
                            "rationale": "unclear",
                        },
                        {"step_id": "not_a_step", "status": "completed", "confidence": 1},
                    ],
                    "limitations": ["the right rail is out of frame"],
                }
            )
        )

    provider = build(settings, handler)
    observations = asyncio.run(
        provider.observe_learner_window(
            ObserveRequest(
                video=prepared.video,
                window=prepared.windows[0],
                frames=prepared.video.frames[:2],
                steps=steps,
                skill_title="Light an LED",
            )
        )
    )
    assert [o.step_id for o in observations] == ["led", "resistor"]
    assert observations[1].status.value == "uncertain", "an unknown status is not a claim"
    assert observations[1].confidence == 1.0
    assert all(o.provenance is Provenance.LIVE for o in observations)
    asyncio.run(provider.aclose())


def test_a_model_cannot_approve_its_own_rules(settings, prepared):
    def handler(_: httpx.Request) -> httpx.Response:
        return chat_response(
            json.dumps(
                {
                    "title": "Light an LED",
                    "summary": "",
                    "objects": [],
                    "steps": [
                        {"step_id": "a", "title": "A", "checkpoint": "a"},
                        {"step_id": "b", "title": "B", "checkpoint": "b"},
                        {"step_id": "c", "title": "C", "checkpoint": "c"},
                    ],
                    "rules": [
                        {
                            "rule_id": "r1",
                            "kind": "safety",
                            "before": "a",
                            "after": "b",
                            "reason": "because",
                            "confirmed_by_expert": True,
                            "proposed_by_model": False,
                        }
                    ],
                }
            )
        )

    provider = build(settings, handler)
    proposal = asyncio.run(
        provider.propose_graph(
            ProposalRequest(
                video=prepared.video,
                descriptions=[],
                key_frames=prepared.video.frames[:2],
            )
        )
    )
    assert proposal.rules[0].confirmed_by_expert is False
    assert proposal.rules[0].proposed_by_model is True
    assert all(step.proposed_by_model for step in proposal.steps)
    asyncio.run(provider.aclose())


def test_secrets_are_not_written_to_the_health_detail(settings):
    provider = build(settings, lambda _: chat_response("{}"))
    detail = provider.health()
    assert "test-key" not in detail.detail
    assert detail.provenance_label is Provenance.LIVE
    asyncio.run(provider.aclose())
