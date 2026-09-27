"""Accept media, sample frames with their true timestamps, and group windows.

OpenCV is the only hard requirement; ffmpeg is never invoked. Frame timestamps
come from the container (CAP_PROP_POS_MSEC) rather than from the sample index,
so a variable-frame-rate phone recording still yields evidence a human can seek
to. When the container reports no timestamp at all, the reader falls back to
frame-index division and records that in the returned limitations.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.config import Settings, get_settings
from app.domain.models import EvidenceRef, Frame, VideoMeta, Window
from app.services.storage import Store, new_id

ALLOWED_SUFFIXES = {".mp4", ".mov", ".webm"}
ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-m4v",
    "application/octet-stream",  # some browsers send this for .mov
}


class MediaError(ValueError):
    """A problem with the uploaded media that the user can act on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExtractionResult:
    video: VideoMeta
    windows: list[Window]
    limitations: list[str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_media_path(relative: str, settings: Settings | None = None) -> Path:
    """Resolve a media-relative path, refusing anything outside the media root."""
    settings = settings or get_settings()
    root = settings.media_root.resolve()
    cleaned = relative.replace("\\", "/").lstrip("/")
    if not cleaned or cleaned.startswith("."):
        raise MediaError("bad_path", "Invalid media path.")
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise MediaError("bad_path", "Media path escapes the media directory.") from exc
    return candidate


def validate_upload(filename: str, content_type: str, size_bytes: int,
                    settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise MediaError(
            "unsupported_media",
            f"Upload an .mp4, .mov, or .webm file. Received {suffix or 'no extension'}.",
        )
    if content_type and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise MediaError(
            "unsupported_media",
            f"Unsupported content type {content_type}.",
        )
    if size_bytes <= 0:
        raise MediaError("empty_media", "The uploaded file is empty.")
    if size_bytes > settings.max_upload_bytes:
        raise MediaError(
            "media_too_large",
            f"The file is {size_bytes / 1_048_576:.1f} MB; the limit is "
            f"{settings.max_upload_mb} MB.",
        )


def probe(path: Path) -> tuple[float, float, int, int, int]:
    """Return (duration_s, fps, width, height, frame_count) or raise MediaError."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise MediaError(
            "unreadable_media",
            "This file could not be decoded as video. It may be corrupt or use an "
            "unsupported codec.",
        )
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        ok, first = capture.read()
        if not ok or first is None:
            raise MediaError(
                "unreadable_media",
                "The file has no readable video frames.",
            )
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        return duration, fps, width, height, frame_count
    finally:
        capture.release()


def _resize(image: np.ndarray, long_side: int) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= long_side:
        return image
    scale = long_side / float(longest)
    return cv2.resize(
        image,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def store_upload(
    source: Path,
    filename: str,
    content_type: str,
    settings: Settings | None = None,
    store: Store | None = None,
    scenario_hint: str | None = None,
) -> VideoMeta:
    """Copy an accepted upload into the media root and record its metadata."""
    settings = settings or get_settings()
    store = store or Store(settings)
    size_bytes = source.stat().st_size
    validate_upload(filename, content_type, size_bytes, settings)

    duration, fps, width, height, _count = probe(source)

    video_id = new_id("vid")
    target_dir = settings.media_root / video_id
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    target = target_dir / f"source{suffix}"
    shutil.copyfile(source, target)

    video = VideoMeta(
        video_id=video_id,
        filename=Path(filename).name,
        content_type=content_type or "video/mp4",
        size_bytes=size_bytes,
        duration_s=duration,
        fps_source=fps,
        width=width,
        height=height,
        sha256=sha256_file(target),
        path=f"{video_id}/{target.name}",
        sample_fps=settings.sample_fps,
        scenario_hint=scenario_hint,
    )
    store.save_video(video)
    return video


def extract_frames(
    video: VideoMeta,
    settings: Settings | None = None,
    store: Store | None = None,
) -> ExtractionResult:
    """Sample frames at the configured rate, preserving source timestamps."""
    settings = settings or get_settings()
    store = store or Store(settings)
    source = safe_media_path(video.path, settings)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        raise MediaError("unreadable_media", "The stored video could not be reopened.")

    limitations: list[str] = []
    frames_dir = settings.media_root / video.video_id / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    interval = 1.0 / max(settings.sample_fps, 0.01)
    frames: list[Frame] = []
    next_sample_at = 0.0
    frame_index = 0
    used_fallback_time = False
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), settings.jpeg_quality]
    last_timestamp = 0.0

    try:
        while True:
            ok, image = capture.read()
            if not ok or image is None:
                break
            pos_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            # A first frame legitimately reports 0 ms; only a later frame still
            # reporting nothing means the container has no timestamps.
            if pos_ms is None or pos_ms < 0 or (pos_ms == 0 and frame_index > 0):
                fps = video.fps_source or settings.sample_fps
                timestamp = frame_index / max(fps, 0.01)
                used_fallback_time = True
            else:
                timestamp = pos_ms / 1000.0
            # Non-monotonic containers exist; never let evidence times go backwards.
            timestamp = max(timestamp, last_timestamp)
            last_timestamp = timestamp
            frame_index += 1

            if timestamp + 1e-6 < next_sample_at:
                continue
            next_sample_at = timestamp + interval

            resized = _resize(image, settings.frame_size)
            ok_encode, buffer = cv2.imencode(".jpg", resized, encode_params)
            if not ok_encode:
                limitations.append(f"A frame at {timestamp:.2f}s could not be encoded.")
                continue
            payload = buffer.tobytes()
            sample_index = len(frames)
            name = f"f{sample_index:05d}_{int(round(timestamp * 1000)):08d}.jpg"
            (frames_dir / name).write_bytes(payload)
            frames.append(
                Frame(
                    index=sample_index,
                    timestamp_s=round(timestamp, 3),
                    media_path=f"{video.video_id}/frames/{name}",
                    sha256=sha256_bytes(payload),
                )
            )
    finally:
        capture.release()

    if not frames:
        raise MediaError(
            "no_frames",
            "No frames could be sampled from this video.",
        )
    if used_fallback_time:
        limitations.append(
            "The container reported no frame timestamps, so evidence times were "
            "derived from the frame rate and may drift."
        )

    duration = video.duration_s or (frames[-1].timestamp_s + interval)
    updated = video.model_copy(
        update={"frames": frames, "duration_s": round(duration, 3)}
    )
    store.save_video(updated)
    windows = build_windows(updated, settings)
    return ExtractionResult(video=updated, windows=windows, limitations=limitations)


def build_windows(video: VideoMeta, settings: Settings | None = None) -> list[Window]:
    """Group sampled frames into overlapping windows of source time."""
    settings = settings or get_settings()
    if not video.frames:
        return []
    span = max(settings.window_seconds, 0.5)
    overlap = min(max(settings.window_overlap, 0.0), span - 0.1)
    stride = span - overlap
    end_time = video.frames[-1].timestamp_s

    windows: list[Window] = []
    start = video.frames[0].timestamp_s
    index = 0
    while start <= end_time + 1e-6:
        stop = start + span
        indexes = [
            frame.index
            for frame in video.frames
            if start - 1e-6 <= frame.timestamp_s < stop - 1e-6
        ]
        if not indexes and windows:
            break
        if indexes:
            index += 1
            windows.append(
                Window(
                    window_id=f"w{index:03d}",
                    t_start=round(start, 3),
                    t_end=round(min(stop, end_time + 1e-3), 3),
                    frame_indexes=indexes,
                )
            )
        start += stride
        if stride <= 0:
            break
    return windows


def window_frames(video: VideoMeta, window: Window) -> list[Frame]:
    by_index = {frame.index: frame for frame in video.frames}
    return [by_index[i] for i in window.frame_indexes if i in by_index]


def pick_frames(frames: list[Frame], limit: int) -> list[Frame]:
    """Evenly spread `limit` frames across a window, keeping first and last."""
    if limit <= 0 or not frames:
        return []
    if len(frames) <= limit:
        return frames
    step = (len(frames) - 1) / (limit - 1) if limit > 1 else 0
    chosen = [frames[int(round(i * step))] for i in range(limit)]
    unique: list[Frame] = []
    for frame in chosen:
        if not unique or unique[-1].index != frame.index:
            unique.append(frame)
    return unique


def evidence_for_window(video: VideoMeta, window: Window) -> EvidenceRef:
    frames = window_frames(video, window)
    return EvidenceRef(
        video_id=video.video_id,
        t_start=window.t_start,
        t_end=window.t_end,
        frame_path=frames[0].media_path if frames else None,
    )


def locate_evidence(
    video: VideoMeta, t_start: float, t_end: float, note: str | None = None
) -> EvidenceRef:
    """Build an evidence reference and attach the nearest sampled frame."""
    nearest: Frame | None = None
    best = float("inf")
    for frame in video.frames:
        distance = abs(frame.timestamp_s - t_start)
        if distance < best:
            best = distance
            nearest = frame
    return EvidenceRef(
        video_id=video.video_id,
        t_start=max(0.0, round(t_start, 3)),
        t_end=max(round(t_start, 3), round(t_end, 3)),
        frame_path=nearest.media_path if nearest else None,
        note=note,
    )
