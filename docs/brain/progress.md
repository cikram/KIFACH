# Progress and handoff

## 2026-09-27 — scaffold

- The folder began with an empty `AGENTS.md` and a `CLAUDE.md` pointer. Initialized a Git repository on `main` for team collaboration.
- Read the selected idea and brainstorming discussions. Captured the product brief, candidate workflow, demo and evaluation ideas, open decisions, and source links in `docs/brain/`.
- Replaced the initial pseudo sketches with Python modules under the requested `backend/app/` layout and a blank React frontend under `frontend/`. The backend functions and frontend product components had no behavior.

## 2026-09-27 — working prototype

The whole loop runs end to end. `python run.py` serves the API and the built
frontend on port 8000; `python run.py --check` prints the active configuration.

**What exists now**

- **Shared contract** in `backend/app/domain/models.py`, with the frontend's
  TypeScript generated from it by `scripts/gen_types.py` and checked in the test
  suite.
- **Media** — `services/video.py` samples frames at their true container
  timestamps, resizes, encodes JPEG, and groups overlapping windows. Path
  traversal is refused in one place.
- **Providers** — `providers/http_vlm.py` (NVIDIA NIM and any OpenAI-compatible
  endpoint), `providers/mock.py` (scripted, offline), `providers/cache.py`
  (genuine responses on disk). Selection: explicit `KIFACH_PROVIDER`, else a
  NVIDIA key, else mock.
- **Teach pipeline** — `services/skill_compiler.py`: window descriptions →
  proposal → validation → one bounded repair → flagged draft. Streams SSE.
- **Review** — `domain/skill_graph.py`: validation, cycle detection in human
  terms, review bookkeeping, and publication that refuses until every proposed
  rule is confirmed and every step has a checkpoint.
- **Verify pipeline** — `services/observation_extractor.py`: per-window
  observation, normalization, and the engine re-run after each window so the
  stream and the stored verdict are the same computation.
- **Engine** — `domain/verifier.py`, pure Python, 96% covered, replay-identical.
- **Frontend** — React + TypeScript strict: library, teach, review, practice,
  verdict, live, demo. Dark/light theming with CSS variables.

**Verified on this machine (2026-09-27)**

- `pytest backend/tests`: 110 passed, 92% coverage; also 110 passed with all
  non-loopback sockets blocked.
- Frontend: typecheck clean, lint clean, 24 unit tests, production build.
- Playwright: 3 specs pass, covering the full loop, all five verdict cases, an
  evidence click that seeks the video, Demo Mode provenance, and phone width.
- Replay mode with a fake key and no network fails with a clear message instead
  of fabricating a result.

## Known gaps

1. **No live model call has ever been made from this build** — no credentials
   were available. Every result in the repository is `MOCK`. The provider path is
   tested offline against a stub transport.
2. **No real footage.** The six bundled clips are drawn fixtures.
3. **Live mode has never seen a real camera.** Its WebSocket protocol is tested
   with synthetic frames.

## Next checkpoint

1. Set `NVIDIA_API_KEY`, teach from real footage, and record what the model
   actually gets right and wrong (`BUILD_REPORT.md` section 5 has the model id
   and input format already confirmed against NVIDIA's docs).
2. Record the six clips in `samples/RECORDING_GUIDE.md` and re-run the loop.
3. Consider expert-drawn checkpoint regions to make `absent` observations
   trustworthy.
