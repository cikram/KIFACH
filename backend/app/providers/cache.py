"""On-disk cache of genuine model responses.

A cached entry records which provider and model produced it, so replay can label
results CACHED rather than pretending they were produced live. The key covers
everything that could change an answer: provider, model, prompt version, request
parameters, task, and the hashes of the exact frames sent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.storage import write_json_atomic


def cache_key(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    task: str,
    frame_hashes: list[str],
    params: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "task": task,
            "frames": frame_hashes,
            "params": params,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]


class ResponseCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.cache_root
        self.mode = settings.resolved_cache_mode()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    @property
    def reads_enabled(self) -> bool:
        return self.mode in ("on", "replay")

    @property
    def writes_enabled(self) -> bool:
        return self.mode == "on"

    @property
    def network_allowed(self) -> bool:
        return self.mode != "replay"

    def get(self, key: str) -> dict | None:
        if not self.reads_enabled:
            return None
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                entry = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return entry.get("payload")

    def put(self, key: str, payload: dict, *, provider: str, model: str, task: str) -> None:
        if not self.writes_enabled:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            self._path(key),
            {
                "provider": provider,
                "model": model,
                "task": task,
                "origin": "live_model_response",
                "payload": payload,
            },
        )
