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

## 2026-09-27 — Runnable backend scaffold

- **Choice:** Use a local Python standard library HTTP server with a `/health` endpoint as the temporary backend run path.
- **Reason:** It lets the team create a virtual environment and start a verifiable process without adding dependencies or choosing the product API framework prematurely.
- **Scope:** Teach, review, and practice remain unimplemented; replace this server when the API transport is chosen.

## 2026-09-27 — FastAPI backend

- **Choice:** Replace the temporary standard library server with FastAPI and run it through Uvicorn.
- **Reason:** The user chose FastAPI for the backend. This provides an HTTP framework while product routes and data shapes are still being designed.
- **Scope:** `/health` is the only route currently implemented.
