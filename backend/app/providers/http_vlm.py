"""Real vision-language provider over an OpenAI-compatible chat endpoint.

NVIDIA's hosted NIM catalogue and self-hosted VLM NIMs both expose
`POST {base_url}/chat/completions` and accept frames as `image_url` parts whose
url is a `data:image/jpeg;base64,...` URI (see BUILD_REPORT.md for the exact
documentation consulted). The generic OpenAI-compatible provider is the same
code with different credentials, so both share this class.

Everything fallible is bounded: a timeout, retries with exponential backoff on
429 and 5xx, a concurrency limit, one JSON repair re-ask, and a reduced image
count if the server rejects the payload. A window that still fails is reported
as uncertain rather than dropped.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.domain.models import (
    EvidenceRef,
    Frame,
    GraphProposal,
    Observation,
    ObservationStatus,
    Provenance,
    ProviderHealth,
    WindowDescription,
)
from app.prompts import (
    LEARNER_SYSTEM,
    OBSERVER_SYSTEM,
    PROMPT_VERSION,
    PROPOSAL_SYSTEM,
    expert_window_prompt,
    learner_window_prompt,
    proposal_prompt,
    repair_prompt,
)
from app.providers.base import (
    CacheMiss,
    ObserveRequest,
    ProposalRequest,
    ProviderError,
    WindowRequest,
)
from app.providers.cache import ResponseCache, cache_key
from app.services.video import safe_media_path

log = logging.getLogger("kifach.provider")

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
MIN_STEPS = 3
MAX_STEPS = 8


def strip_fences(text: str) -> str:
    cleaned = _FENCE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


class HttpVlmProvider:
    """Shared implementation for the NVIDIA and generic OpenAI-compatible providers."""

    def __init__(
        self,
        settings: Settings,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.cache = ResponseCache(settings)
        self._client = client
        self._owns_client = client is None
        self._semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))
        self.images_per_call = max(1, settings.max_images_per_call)
        self.notes: list[str] = []

    # -- plumbing ----------------------------------------------------------

    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.request_timeout_s),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def health(self) -> ProviderHealth:
        configured = bool(self.api_key and self.base_url)
        return ProviderHealth(
            provider=self.name,
            model=self.model,
            configured=configured,
            cache_mode=self.cache.mode,
            provenance_label=(
                Provenance.CACHED if self.cache.mode == "replay" else Provenance.LIVE
            ),
            detail=(
                f"{self.base_url} ({'replay: no network calls' if self.cache.mode == 'replay' else 'live calls enabled'})"
                if configured
                else "Missing API key or base URL."
            ),
        )

    def _params(self) -> dict[str, Any]:
        return {
            "temperature": self.settings.temperature,
            "max_tokens": 1400,
            "images": self.images_per_call,
        }

    @staticmethod
    def _encode(frames: list[Frame], settings: Settings) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        for frame in frames:
            path = safe_media_path(frame.media_path, settings)
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{payload}"},
                }
            )
        return parts

    async def _post(self, body: dict[str, Any]) -> str:
        """One chat completion, with bounded retries. Returns the message text."""
        if not self.cache.network_allowed:
            raise CacheMiss("Replay mode forbids network calls.")
        if not self.api_key:
            raise ProviderError(f"{self.name} has no API key configured.")

        url = f"{self.base_url}/chat/completions"
        delay = 1.0
        last_error = "unknown error"
        for attempt in range(1, self.settings.max_retries + 1):
            started = time.monotonic()
            try:
                async with self._semaphore:
                    response = await self.client().post(url, json=body)
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc.__class__.__name__}"
                log.warning("%s attempt %d failed: %s", self.name, attempt, last_error)
            else:
                elapsed = (time.monotonic() - started) * 1000
                request_id = response.headers.get(
                    "x-request-id"
                ) or response.headers.get("nvcf-reqid", "-")
                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usage") or {}
                    log.info(
                        "%s model=%s status=200 latency_ms=%.0f tokens=%s request_id=%s",
                        self.name,
                        self.model,
                        elapsed,
                        usage.get("total_tokens", "-"),
                        request_id,
                    )
                    choices = data.get("choices") or []
                    if not choices:
                        raise ProviderError("The model returned no choices.")
                    return str(choices[0].get("message", {}).get("content", ""))

                body_excerpt = response.text[:300]
                log.warning(
                    "%s model=%s status=%d latency_ms=%.0f request_id=%s body=%s",
                    self.name,
                    self.model,
                    response.status_code,
                    elapsed,
                    request_id,
                    body_excerpt,
                )
                if response.status_code in (400, 413, 422) and self.images_per_call > 1:
                    # The server rejected the payload; try again with fewer frames.
                    self.images_per_call = max(1, self.images_per_call // 2)
                    note = (
                        f"{self.name} rejected the request with HTTP "
                        f"{response.status_code}; reduced images per call to "
                        f"{self.images_per_call}."
                    )
                    if note not in self.notes:
                        self.notes.append(note)
                    raise ProviderError(note, retryable=False)
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                else:
                    raise ProviderError(
                        f"{self.name} returned HTTP {response.status_code}: "
                        f"{body_excerpt}"
                    )
            if attempt < self.settings.max_retries:
                await asyncio.sleep(delay)
                delay *= 2
        raise ProviderError(
            f"{self.name} did not answer after {self.settings.max_retries} attempts "
            f"({last_error}).",
            retryable=True,
        )

    async def _ask_json(
        self,
        *,
        system: str,
        user: str,
        frames: list[Frame],
        task: str,
    ) -> dict:
        """Cached, validated JSON round trip with one repair re-ask."""
        frames = frames[: self.images_per_call]
        key = cache_key(
            provider=self.name,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            task=task,
            frame_hashes=[f.sha256 for f in frames],
            params={**self._params(), "user": user[:2000]},
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if not self.cache.network_allowed:
            raise CacheMiss(
                f"No cached response for {task} and replay mode makes no network calls."
            )

        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        content.extend(self._encode(frames, self.settings))
        body = {
            "model": self.model,
            "temperature": self.settings.temperature,
            "max_tokens": 1400,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        }

        raw = await self._post(body)
        try:
            parsed = json.loads(strip_fences(raw))
            if not isinstance(parsed, dict):
                raise ValueError("The model returned JSON that is not an object.")
        except (json.JSONDecodeError, ValueError) as exc:
            repair_body = dict(body)
            repair_body["messages"] = [
                *body["messages"],
                {"role": "assistant", "content": raw[:2000]},
                {"role": "user", "content": repair_prompt(errors=str(exc))},
            ]
            raw_retry = await self._post(repair_body)
            try:
                parsed = json.loads(strip_fences(raw_retry))
                if not isinstance(parsed, dict):
                    raise ValueError("Still not a JSON object.")
            except (json.JSONDecodeError, ValueError) as exc2:
                raise ProviderError(
                    f"The model did not return valid JSON for {task}: {exc2}"
                ) from exc2

        self.cache.put(key, parsed, provider=self.name, model=self.model, task=task)
        return parsed

    # -- provider interface ------------------------------------------------

    async def describe_expert_window(self, request: WindowRequest) -> WindowDescription:
        from app.services.video import evidence_for_window

        user = expert_window_prompt(
            t_start=request.window.t_start,
            t_end=request.window.t_end,
            frame_count=min(len(request.frames), self.images_per_call),
            task_hint=request.task_hint,
        )
        payload = await self._ask_json(
            system=OBSERVER_SYSTEM,
            user=user,
            frames=request.frames,
            task="expert_window",
        )
        provenance = (
            Provenance.CACHED if self.cache.mode == "replay" else Provenance.LIVE
        )

        def as_list(value: Any) -> list[str]:
            if isinstance(value, list):
                return [str(v) for v in value if str(v).strip()]
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []

        return WindowDescription(
            window_id=request.window.window_id,
            t_start=request.window.t_start,
            t_end=request.window.t_end,
            objects=as_list(payload.get("objects")),
            actions=as_list(payload.get("actions")),
            changes=as_list(payload.get("changes")),
            candidate_steps=as_list(payload.get("candidate_steps")),
            limitations=as_list(payload.get("limitations")),
            evidence=evidence_for_window(request.video, request.window),
            provenance=provenance,
        )

    async def propose_graph(self, request: ProposalRequest) -> GraphProposal:
        lines: list[str] = []
        for description in request.descriptions:
            lines.append(
                f"[{description.t_start:.1f}s-{description.t_end:.1f}s] "
                f"objects: {', '.join(description.objects) or '-'} | "
                f"actions: {', '.join(description.actions) or '-'} | "
                f"changes: {', '.join(description.changes) or '-'} | "
                f"possible steps: {', '.join(description.candidate_steps) or '-'} | "
                f"could not see: {', '.join(description.limitations) or '-'}"
            )
        user = proposal_prompt(
            windows_text="\n".join(lines), min_steps=MIN_STEPS, max_steps=MAX_STEPS
        )
        payload = await self._ask_json(
            system=PROPOSAL_SYSTEM,
            user=user,
            frames=request.key_frames,
            task="graph_proposal",
        )
        try:
            proposal = GraphProposal.model_validate(payload)
        except ValidationError as exc:
            repaired = await self._ask_json(
                system=PROPOSAL_SYSTEM,
                user=user + "\n\n" + repair_prompt(errors=str(exc)),
                frames=request.key_frames,
                task="graph_proposal_repair",
            )
            proposal = GraphProposal.model_validate(repaired)
        # A real model must not be able to mark its own rules as approved.
        return proposal.model_copy(
            update={
                "rules": [
                    rule.model_copy(
                        update={"proposed_by_model": True, "confirmed_by_expert": False}
                    )
                    for rule in proposal.rules
                ],
                "steps": [
                    step.model_copy(update={"proposed_by_model": True})
                    for step in proposal.steps
                ],
            }
        )

    async def observe_learner_window(
        self, request: ObserveRequest
    ) -> list[Observation]:
        from app.services.video import evidence_for_window

        user = learner_window_prompt(
            t_start=request.window.t_start,
            t_end=request.window.t_end,
            frame_count=min(len(request.frames), self.images_per_call),
            skill_title=request.skill_title,
            steps=request.steps,
        )
        payload = await self._ask_json(
            system=LEARNER_SYSTEM,
            user=user,
            frames=request.frames,
            task="learner_window",
        )
        provenance = (
            Provenance.CACHED if self.cache.mode == "replay" else Provenance.LIVE
        )
        evidence: EvidenceRef = evidence_for_window(request.video, request.window)
        valid_ids = {step.step_id for step in request.steps}

        observations: list[Observation] = []
        raw_items = payload.get("observations")
        if not isinstance(raw_items, list):
            raw_items = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            step_id = str(item.get("step_id", "")).strip()
            if step_id not in valid_ids:
                continue
            status_raw = str(item.get("status", "")).strip().lower()
            try:
                status = ObservationStatus(status_raw)
            except ValueError:
                status = ObservationStatus.UNCERTAIN
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = min(max(confidence, 0.0), 1.0)
            observations.append(
                Observation(
                    observation_id=f"{request.window.window_id}_{step_id}_{index}",
                    window_id=request.window.window_id,
                    step_id=step_id,
                    status=status,
                    confidence=confidence,
                    t_start=request.window.t_start,
                    t_end=request.window.t_end,
                    evidence=evidence,
                    rationale=str(item.get("rationale", ""))[:400],
                    provenance=provenance,
                )
            )
        return observations
