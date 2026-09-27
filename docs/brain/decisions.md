# Decisions

Record a choice here only when the team has made it. Include date, reason, and any alternative that mattered. Keep unchosen ideas in [brainstorm.md](brainstorm.md) and open questions in [the docs index](../README.md).

## 2026-09-27 — Project scope

- **Choice:** Build KIFACH around learning a physical procedure from an expert demonstration and assessing a learner's attempt with inspectable evidence.
- **Reason:** This is the selected hackathon idea and its central demo loop.
- **Source:** [Selected idea](https://chatgpt.com/s/t_6ab8681fd3708191bd59df08fbd8efa2).

## 2026-09-27 — Scaffold before implementation

- **Choice:** Establish notes and actual source stubs with empty behavior first. Use Python for the backend and React for the frontend, as specified by the user. Defer the API, model, final schema, and specific demo task.
- **Reason:** The team needs a shared starting point for splitting work without locking in untested architecture.
- **Source:** Project setup request and the user's Python/React clarification.

## 2026-09-27 — Backend folder layout

- **Choice:** Use `backend/app/` with `api/`, `domain/`, `prompts/`, `services/`, and `main.py`.
- **Reason:** This is the user's requested structure for splitting backend work.
- **Source:** User-supplied structure image and follow-up instruction.

## 2026-09-27 — Runnable backend scaffold *(superseded)*

- **Choice:** Use a local Python standard library HTTP server with a `/health` endpoint as the temporary backend run path.
- **Reason:** It let the team create a virtual environment and start a verifiable process without adding dependencies or choosing the product API framework prematurely.
- **Superseded by:** the FastAPI entry below.

## 2026-09-27 — FastAPI backend

- **Choice:** Replace the temporary standard library server with FastAPI, run through Uvicorn.
- **Reason:** The user chose FastAPI for the backend.
- **Scope then:** `/health` was the only route. The full REST, SSE, and WebSocket surface was built on this choice later the same day.

## 2026-09-27 — The model proposes; reviewed code decides

- **Choice:** The vision model only describes what is visible and proposes a draft procedure. A pure-Python engine, running against an expert-reviewed procedure, decides every step state and the verdict.
- **Reason:** If the model both observes and judges, a misread frame and a real learner error are indistinguishable. Splitting them makes each verdict replayable and inspectable.
- **Consequence:** `POST /api/attempts/{id}/replay` re-runs the stored observation log and must reproduce the result exactly. The engine has no network, disk, clock, or randomness.

## 2026-09-27 — Three verdicts, and absence is not silence

- **Choice:** `VERIFIED`, `NOT_VERIFIED`, and `INCONCLUSIVE`. A step may be reported as skipped only when an observation explicitly says the checkpoint area was visible and the expected result was not there.
- **Reason:** "We never saw the resistor" is not evidence that the resistor is missing. Failing a learner on missing footage would be the most damaging thing this product could do.
- **Alternative rejected:** A pass/fail score with a confidence number, which hides the difference between a mistake and a bad camera angle.

## 2026-09-27 — Publication requires human confirmation of every rule

- **Choice:** A draft cannot be published until every model-proposed ordering or safety rule is confirmed or removed, and every step has a checkpoint. Proposals are labelled as proposals in the UI until then.
- **Reason:** A rule nobody read is not a standard to judge anyone against.

## 2026-09-27 — Stack

- **Choice:** FastAPI + Pydantic v2 + OpenCV (headless) on the backend; Vite + React + TypeScript strict + Tailwind + @xyflow/react on the frontend; JSON files under `data/`; pytest and Playwright.
- **Reason:** Matches the delivery brief, needs no ffmpeg or GPU, and runs from one command on Windows, macOS, and Linux.
- **Detail:** A tiny hash router replaced a routing library — six screens, no nested routes.

## 2026-09-27 — Demo fixtures are VP8 WebM, not MP4

- **Choice:** `scripts/make_synthetic_video.py` writes VP8 in WebM.
- **Reason:** OpenCV's `mp4v` writer produces MPEG-4 Part 2, which browsers cannot decode, so evidence clicks seeked a blank player. OpenCV here cannot write H.264 without the OpenH264 DLL. VP8/WebM is the one format OpenCV writes and reads and every target browser plays.

## 2026-09-27 — The offline mock refuses unknown footage

- **Choice:** The mock provider answers only for media it can identify (scenario hint, registered sha256, or a recognisable sample filename). For anything else it raises an actionable error.
- **Reason:** Inventing an assessment for a judge's own video would be a fabricated model result wearing a MOCK badge.
