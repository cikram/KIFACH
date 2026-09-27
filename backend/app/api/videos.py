"""Media upload and safe media serving."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import settings_dep, store_dep
from app.api.errors import ApiError, bad_request, not_found
from app.config import Settings
from app.domain.models import VideoMeta
from app.services.storage import NotFound, Store, is_safe_id
from app.services.video import MediaError, safe_media_path, store_upload

router = APIRouter(tags=["media"])

CHUNK = 1024 * 1024

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}


@router.post("/videos", response_model=VideoMeta)
async def upload_video(
    file: UploadFile = File(...),
    scenario: str | None = Form(default=None),
    settings: Settings = Depends(settings_dep),
    store: Store = Depends(store_dep),
) -> VideoMeta:
    """Accept a recording and register it. Frames are extracted by the pipelines."""
    filename = file.filename or "upload.mp4"
    suffix = Path(filename).suffix.lower() or ".mp4"
    tmp_dir = Path(tempfile.mkdtemp(prefix="kifach_upload_"))
    tmp_path = tmp_dir / f"upload{suffix}"
    written = 0
    try:
        with open(tmp_path, "wb") as handle:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    raise bad_request(
                        "media_too_large",
                        f"The upload exceeds the {settings.max_upload_mb} MB limit.",
                    )
                handle.write(chunk)
        try:
            return store_upload(
                tmp_path,
                filename,
                file.content_type or "",
                settings,
                store,
                scenario_hint=scenario or None,
            )
        except MediaError as exc:
            raise ApiError(400, exc.code, exc.message) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/videos/{video_id}", response_model=VideoMeta)
async def get_video(
    video_id: str, store: Store = Depends(store_dep)
) -> VideoMeta:
    if not is_safe_id(video_id):
        raise bad_request("invalid_id", "That video id is not valid.")
    try:
        return store.get_video(video_id)
    except NotFound as exc:
        raise not_found(str(exc)) from exc


@router.get("/media/{path:path}")
async def serve_media(
    path: str, settings: Settings = Depends(settings_dep)
) -> FileResponse:
    """Serve a stored frame or source video, strictly inside the media root."""
    try:
        resolved = safe_media_path(path, settings)
    except MediaError as exc:
        raise ApiError(400, exc.code, exc.message) from exc
    if not resolved.is_file():
        raise not_found("That media file does not exist.")
    media_type = MEDIA_TYPES.get(resolved.suffix.lower(), "application/octet-stream")
    return FileResponse(resolved, media_type=media_type)
