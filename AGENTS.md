# KIFACH project guidance

KIFACH is an 11-hour hackathon prototype: an expert demonstrates a physical task, the system derives a reviewable procedure, and a learner's attempt is assessed with evidence. Read [docs/README.md](docs/README.md) before changing the product shape.

## Working rules

- Keep the path from expert demonstration to learner feedback demoable end to end. Preserve timestamps or other evidence that lets a human inspect an assessment.
- Treat model observations as fallible. Keep observation, procedure construction, and assessment separate, and represent uncertainty when evidence is insufficient.
- The backend is FastAPI + Pydantic v2 + OpenCV; the frontend is Vite + React + TypeScript (strict). Frontend types are generated from the backend models by `scripts/gen_types.py`, and `pytest` fails when they drift. See [docs/brain/components.md](docs/brain/components.md) for what owns what.
- Record confirmed product or technical decisions and their reasons in [docs/brain/decisions.md](docs/brain/decisions.md). Keep unresolved questions in [docs/README.md](docs/README.md) and proposals in [docs/brain/brainstorm.md](docs/brain/brainstorm.md). Update [docs/brain/progress.md](docs/brain/progress.md) after meaningful progress so a new session can resume quickly.
- When implementing a component, agree on the shared input and output shapes with adjacent workstreams before depending on them. Keep `README.md` aligned with each runnable path.

## Current state

The full loop works: `python run.py` serves the API and the built frontend on port 8000. With no credentials it runs the scripted offline provider and labels every result `MOCK`.

- Run the tests before and after a change: `python -m pytest backend/tests -q`, `npm --prefix frontend run typecheck`, `npm --prefix frontend test`, `npm --prefix frontend run e2e`.
- Never present mock, synthetic, or cached output as a live model result. The `LIVE` / `CACHED` / `MOCK` labels are load-bearing.
- No live model call has been made from this repository yet; see [BUILD_REPORT.md](BUILD_REPORT.md) for exactly what is and is not proven.

`CLAUDE.md` points here.
