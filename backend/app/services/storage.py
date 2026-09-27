"""JSON-file persistence for the prototype.

Writes go to a temporary file in the same directory and are then replaced into
place, so an interrupted run leaves either the previous record or the new one,
never a truncated one. Ids are time-ordered with a random suffix so listings
sort naturally and two concurrent uploads cannot collide.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.domain.models import Attempt, SkillGraph, VideoMeta

ModelT = TypeVar("ModelT", bound=BaseModel)

_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


class StorageError(RuntimeError):
    pass


class NotFound(StorageError):
    pass


def new_id(prefix: str) -> str:
    stamp = format(int(time.time() * 1000), "x")
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))
    return f"{prefix}_{stamp}{suffix}"


def is_safe_id(value: str) -> bool:
    """Ids appear in filesystem paths, so keep them to a boring alphabet."""
    if not value or len(value) > 80:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in value)


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    data = json.dumps(payload, indent=2, sort_keys=False, default=str)
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class Store:
    """Directory-backed collections of Pydantic records."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()

    # -- generic -----------------------------------------------------------

    def _dir(self, collection: str) -> Path:
        path = self.settings.data_root / collection
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _path(self, collection: str, record_id: str) -> Path:
        if not is_safe_id(record_id):
            raise StorageError(f"Unsafe record id: {record_id!r}")
        return self._dir(collection) / f"{record_id}.json"

    def save(self, collection: str, record_id: str, model: BaseModel) -> None:
        write_json_atomic(self._path(collection, record_id), model.model_dump(mode="json"))

    def load(self, collection: str, record_id: str, model_type: type[ModelT]) -> ModelT:
        path = self._path(collection, record_id)
        if not path.exists():
            raise NotFound(f"{collection[:-1] if collection.endswith('s') else collection} {record_id} not found")
        try:
            return model_type.model_validate(read_json(path))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise StorageError(f"Stored record {record_id} is unreadable: {exc}") from exc

    def exists(self, collection: str, record_id: str) -> bool:
        return is_safe_id(record_id) and self._path(collection, record_id).exists()

    def delete(self, collection: str, record_id: str) -> None:
        path = self._path(collection, record_id)
        if path.exists():
            path.unlink()

    def list_all(self, collection: str, model_type: type[ModelT]) -> list[ModelT]:
        records: list[ModelT] = []
        for path in sorted(self._dir(collection).glob("*.json")):
            try:
                records.append(model_type.model_validate(read_json(path)))
            except (ValidationError, json.JSONDecodeError):
                continue  # a half-written or outdated record must not break the list
        return records

    # -- typed helpers -----------------------------------------------------

    def save_video(self, video: VideoMeta) -> None:
        self.save("videos", video.video_id, video)

    def get_video(self, video_id: str) -> VideoMeta:
        return self.load("videos", video_id, VideoMeta)

    def save_skill(self, skill: SkillGraph) -> None:
        self.save("skills", skill.skill_id, skill)

    def get_skill(self, skill_id: str) -> SkillGraph:
        return self.load("skills", skill_id, SkillGraph)

    def list_skills(self) -> list[SkillGraph]:
        return self.list_all("skills", SkillGraph)

    def delete_skill(self, skill_id: str) -> None:
        self.delete("skills", skill_id)

    def save_attempt(self, attempt: Attempt) -> None:
        self.save("attempts", attempt.attempt_id, attempt)

    def get_attempt(self, attempt_id: str) -> Attempt:
        return self.load("attempts", attempt_id, Attempt)

    def list_attempts(self) -> list[Attempt]:
        return self.list_all("attempts", Attempt)

    def attempts_for_skill(self, skill_id: str) -> list[Attempt]:
        return [a for a in self.list_attempts() if a.skill_id == skill_id]

    def latest_attempt(self, skill_id: str) -> Attempt | None:
        attempts = sorted(
            self.attempts_for_skill(skill_id), key=lambda a: a.created_at
        )
        return attempts[-1] if attempts else None


def iter_media_paths(paths: Iterable[str]) -> list[str]:
    """Normalize stored media paths to forward slashes for the API and UI."""
    return [str(p).replace("\\", "/") for p in paths]
