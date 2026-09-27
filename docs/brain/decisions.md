# Decisions

Record a choice here only when the team has made it. Include date, reason, and any alternative that mattered. Keep unchosen ideas in [README.md](README.md).

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
