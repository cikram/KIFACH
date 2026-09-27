"""Media processing, path safety, provider selection, caching, and replay mode."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.config import Settings, get_settings, reset_settings_cache
from app.domain.models import Provenance, VideoMeta
from app.providers import build_provider, provider_label
from app.providers.base import CacheMiss, ProviderError, WindowRequest
from app.providers.cache import ResponseCache, cache_key
from app.providers.http_vlm import HttpVlmProvider, strip_fences
from app.providers.mock import MockProvider, map_step_ids
from app.services.storage import Store, is_safe_id, new_id, write_json_atomic
from app.services.video import (
    MediaError,
    build_windows,
    extract_frames,
    pick_frames,
    safe_media_path,
    store_upload,
    validate_upload,
)
from tests.conftest import sample_path


@pytest.fixture
def expert_video(isolated_settings, store) -> VideoMeta:
    return store_upload(
        sample_path("expert.webm"),
        "expert.webm",
        "video/webm",
        isolated_settings,
        store,
    )


# --- media ---------------------------------------------------------------


def test_extraction_keeps_real_source_timestamps(isolated_settings, store, expert_video):
    result = extract_frames(expert_video, isolated_settings, store)
    frames = result.video.frames
    assert len(frames) >= 10
    assert frames[0].timestamp_s == 0.0
    # 2 fps sampling of a 24 second clip, within one sample either way.
    assert 46 <= len(frames) <= 50
    assert all(
        later.timestamp_s > earlier.timestamp_s
        for earlier, later in zip(frames, frames[1:])
    )
    # Timestamps come from the container, not from index / fps arithmetic alone.
    assert result.limitations == []
    assert all(frame.sha256 for frame in frames)


def test_windows_overlap_as_configured(isolated_settings, store, expert_video):
    result = extract_frames(expert_video, isolated_settings, store)
    windows = result.windows
    assert len(windows) >= 5
    first, second = windows[0], windows[1]
    assert first.t_end - first.t_start == pytest.approx(
        isolated_settings.window_seconds, abs=0.2
    )
    assert second.t_start - first.t_start == pytest.approx(
        isolated_settings.window_seconds - isolated_settings.window_overlap, abs=0.2
    )
    # Consecutive windows deliberately share their overlap, which is why the
    # engine has to treat one event seen twice as one confirmation.
    assert set(first.frame_indexes) & set(second.frame_indexes)


def test_pick_frames_spreads_across_a_window(isolated_settings, store, expert_video):
    result = extract_frames(expert_video, isolated_settings, store)
    frames = result.video.frames
    picked = pick_frames(frames, 4)
    assert len(picked) == 4
    assert picked[0].index == frames[0].index
    assert picked[-1].index == frames[-1].index


def test_build_windows_of_an_empty_video_is_empty(isolated_settings, expert_video):
    assert build_windows(expert_video, isolated_settings) == []


def test_validate_upload_rejects_bad_input(isolated_settings):
    with pytest.raises(MediaError) as unsupported:
        validate_upload("clip.gif", "image/gif", 100, isolated_settings)
    assert unsupported.value.code == "unsupported_media"

    with pytest.raises(MediaError) as empty:
        validate_upload("clip.mp4", "video/mp4", 0, isolated_settings)
    assert empty.value.code == "empty_media"

    with pytest.raises(MediaError) as big:
        validate_upload(
            "clip.mp4", "video/mp4", isolated_settings.max_upload_bytes + 1, isolated_settings
        )
    assert big.value.code == "media_too_large"


@pytest.mark.parametrize(
    "path",
    ["../AGENTS.md", "../../etc/passwd", "..\\..\\AGENTS.md", "", ".hidden/f.jpg"],
)
def test_safe_media_path_refuses_escapes(isolated_settings, path):
    with pytest.raises(MediaError):
        safe_media_path(path, isolated_settings)


def test_safe_media_path_allows_media_files(isolated_settings):
    resolved = safe_media_path("vid_1/frames/f00001.jpg", isolated_settings)
    assert str(resolved).startswith(str(isolated_settings.media_root))

    # A leading slash is stripped rather than rejected; the result still has to
    # land inside the media root.
    rooted = safe_media_path("/vid_1/frames/f00001.jpg", isolated_settings)
    assert str(rooted).startswith(str(isolated_settings.media_root))


def test_ids_are_safe_and_unique():
    ids = {new_id("vid") for _ in range(200)}
    assert len(ids) == 200
    assert all(is_safe_id(value) for value in ids)
    assert not is_safe_id("../escape")
    assert not is_safe_id("")


def test_json_writes_are_atomic(tmp_path):
    target = tmp_path / "record.json"
    write_json_atomic(target, {"a": 1})
    write_json_atomic(target, {"a": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}
    assert list(tmp_path.glob("*.tmp")) == []


# --- provider selection --------------------------------------------------


def test_mock_is_selected_without_credentials(isolated_settings):
    assert isolated_settings.resolved_provider() == "mock"
    assert provider_label(isolated_settings) == "MOCK"
    assert isinstance(build_provider(isolated_settings), MockProvider)


def test_explicit_provider_wins(monkeypatch):
    monkeypatch.setenv("KIFACH_PROVIDER", "mock")
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-key")
    reset_settings_cache()
    settings = get_settings()
    assert settings.resolved_provider() == "mock"
    reset_settings_cache()


def test_a_key_selects_nvidia(monkeypatch):
    monkeypatch.delenv("KIFACH_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-key")
    reset_settings_cache()
    settings = get_settings()
    assert settings.resolved_provider() == "nvidia"
    assert provider_label(settings) == "LIVE"
    provider = build_provider(settings)
    assert isinstance(provider, HttpVlmProvider)
    health = provider.health()
    assert health.configured is True
    assert health.model == settings.vlm_model
    assert "secret-key" not in health.detail
    reset_settings_cache()


def test_replay_mode_labels_results_cached(monkeypatch):
    monkeypatch.delenv("KIFACH_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-key")
    monkeypatch.setenv("KIFACH_CACHE", "replay")
    reset_settings_cache()
    settings = get_settings()
    assert provider_label(settings) == "CACHED"
    assert settings.resolved_cache_mode() == "replay"
    reset_settings_cache()


def test_replay_mode_makes_no_network_call(monkeypatch, tmp_path, expert_video):
    """A missing cache entry must fail loudly, never silently call out."""
    monkeypatch.setenv("KIFACH_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "secret-key")
    monkeypatch.setenv("KIFACH_CACHE", "replay")
    reset_settings_cache()
    settings = get_settings()
    settings.ensure_dirs()
    provider = build_provider(settings)

    async def fail(*_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("replay mode attempted a network call")

    monkeypatch.setattr(HttpVlmProvider, "_post", fail)

    extraction = extract_frames(expert_video, settings, Store(settings))
    request = WindowRequest(
        video=extraction.video,
        window=extraction.windows[0],
        frames=extraction.video.frames[:2],
    )
    with pytest.raises(CacheMiss):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            provider.describe_expert_window(request)
        )
    reset_settings_cache()


# --- cache ---------------------------------------------------------------


def test_cache_key_covers_everything_that_changes_an_answer():
    base = dict(
        provider="nvidia",
        model="m",
        prompt_version="v1",
        task="expert_window",
        frame_hashes=["a", "b"],
        params={"temperature": 0.0},
    )
    key = cache_key(**base)
    assert key == cache_key(**base)
    assert key != cache_key(**{**base, "model": "other"})
    assert key != cache_key(**{**base, "prompt_version": "v2"})
    assert key != cache_key(**{**base, "frame_hashes": ["a", "c"]})
    assert key != cache_key(**{**base, "params": {"temperature": 0.2}})


def test_cache_records_that_an_entry_came_from_a_model(isolated_settings):
    cache = ResponseCache(isolated_settings)
    cache.put("k1", {"objects": []}, provider="nvidia", model="m", task="expert_window")
    stored = json.loads((isolated_settings.cache_root / "k1.json").read_text("utf-8"))
    assert stored["origin"] == "live_model_response"
    assert cache.get("k1") == {"objects": []}


def test_cache_off_stores_nothing(monkeypatch):
    monkeypatch.setenv("KIFACH_CACHE", "off")
    reset_settings_cache()
    settings = get_settings()
    settings.ensure_dirs()
    cache = ResponseCache(settings)
    cache.put("k2", {"a": 1}, provider="p", model="m", task="t")
    assert cache.get("k2") is None
    reset_settings_cache()


def test_strip_fences_recovers_json_from_a_chatty_answer():
    assert json.loads(strip_fences('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(strip_fences('Sure! {"a": 2} Hope that helps.')) == {"a": 2}


# --- mock provider -------------------------------------------------------


def test_mock_refuses_media_it_has_no_script_for(isolated_settings, store):
    provider = MockProvider(isolated_settings)
    unknown = VideoMeta(
        video_id="vid_unknown",
        filename="my-own-recording.webm",
        content_type="video/webm",
        size_bytes=1,
        duration_s=5,
        fps_source=12,
        width=10,
        height=10,
        sha256="f" * 64,
        path="vid_unknown/source.webm",
    )
    assert provider.resolve(unknown) is None
    with pytest.raises(ProviderError) as problem:
        asyncio.run(_propose(provider, unknown))
    assert "no scripted analysis" in str(problem.value)


async def _propose(provider: MockProvider, video: VideoMeta):
    """The mock must refuse rather than invent a procedure for unknown footage."""
    from app.providers.base import ProposalRequest

    return await provider.propose_graph(
        ProposalRequest(video=video, descriptions=[], key_frames=[])
    )


def test_mock_resolves_by_hash_hint_and_filename(isolated_settings, expert_video):
    provider = MockProvider(isolated_settings)
    assert provider.resolve(expert_video).scenario_id == "expert"

    by_hint = expert_video.model_copy(
        update={"scenario_hint": "wrong_order", "filename": "anything.webm"}
    )
    assert provider.resolve(by_hint).scenario_id == "wrong_order"

    by_name = expert_video.model_copy(
        update={"scenario_hint": None, "sha256": "0" * 64, "filename": "uncertain.webm"}
    )
    assert provider.resolve(by_name).scenario_id == "uncertain"


def test_mock_output_is_labelled_mock(isolated_settings, store, expert_video):
    provider = MockProvider(isolated_settings)
    extraction = extract_frames(expert_video, isolated_settings, store)
    description = asyncio.run(
        provider.describe_expert_window(
            WindowRequest(
                video=extraction.video,
                window=extraction.windows[0],
                frames=extraction.video.frames[:2],
            )
        )
    )
    assert description.provenance is Provenance.MOCK
    assert description.objects


def test_step_id_mapping_survives_renaming(isolated_settings):
    from app.domain.models import Step

    steps = [
        Step(step_id="s1", title="Put the LED in place", checkpoint="led seated"),
        Step(step_id="s2", title="Add the resistor", checkpoint="resistor bridges"),
        Step(step_id="s3", title="Wire ground", checkpoint="black jumper"),
        Step(step_id="s4", title="Switch on the power", checkpoint="battery attached"),
        Step(step_id="s5", title="Check it is lit", checkpoint="LED lit"),
    ]
    mapping = map_step_ids(
        ["place_led", "connect_resistor", "connect_ground", "apply_power", "confirm_led"],
        steps,
    )
    assert mapping["connect_resistor"] == "s2"
    assert mapping["apply_power"] == "s4"
    assert mapping["confirm_led"] == "s5"


def test_settings_defaults_match_the_documented_table():
    settings = Settings()  # type: ignore[call-arg]
    assert settings.sample_fps == 2.0
    assert settings.frame_size == 768
    assert settings.window_seconds == 4.0
    assert settings.window_overlap == 1.0
    assert settings.max_upload_mb == 200
    assert settings.jpeg_quality == 85
    assert settings.min_confidence == 0.6
    assert settings.temperature == 0.0
