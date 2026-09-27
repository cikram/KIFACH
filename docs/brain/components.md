# Source layout

The prototype is built. This is where each piece lives and what it owns.

## Backend (`backend/app/`)

| Area | Files | Responsibility |
| --- | --- | --- |
| Shared contract | `domain/models.py` | Every payload the API, engine, and frontend share. `scripts/gen_types.py` generates the TypeScript from it |
| Configuration | `config.py` | One place for every environment variable and default |
| Procedure | `domain/skill_graph.py` | Validation (ids, references, checkpoints, cycles), the bounded repair pass, review bookkeeping, publication |
| Engine | `domain/verifier.py` | The deterministic assessment. Pure Python: no network, disk, clock, or randomness |
| Media | `services/video.py` | Upload validation, frame sampling at true source timestamps, windowing, evidence refs, media path safety |
| Teach | `services/skill_compiler.py` | Expert media -> window descriptions -> proposal -> validation -> flagged draft |
| Verify | `services/observation_extractor.py` | Learner media -> observations -> normalization -> engine -> attempt |
| Jobs | `services/jobs.py` | Background jobs with a replayable SSE event log |
| Storage | `services/storage.py` | Atomic JSON records under `data/`, collision-resistant ids |
| Providers | `providers/http_vlm.py`, `mock.py`, `cache.py`, `scenarios.py` | NVIDIA NIM and OpenAI-compatible endpoints, the scripted offline provider, the response cache, and the demo scripts |
| Prompts | `prompts/__init__.py` | Prompt text plus the JSON shape each answer must match. The version is part of the cache key |
| API | `api/health.py`, `videos.py`, `skills.py`, `runs.py`, `live.py` | REST, SSE, and the live WebSocket. One error shape throughout |
| Entry point | `main.py` | App factory, error handlers, static frontend, `/samples` |

## Frontend (`frontend/src/`)

| Area | Files | Responsibility |
| --- | --- | --- |
| Shell | `App.tsx`, `lib/router.tsx`, `lib/routes.ts` | Header, provider badge, theme, hash routing |
| Contract | `types/api.ts` | Generated from the backend models. Never edited by hand |
| Client | `lib/api.ts` | Every request, with the backend's error code and message preserved |
| Streaming | `hooks/useJobStream.ts` | Resumable SSE with a one-shot state recovery fallback |
| Screens | `views/*.tsx` | Home, Teach, Review, Practice, Verdict, Live, Demo |
| Pieces | `components/*.tsx` | Evidence player, procedure graph, review editor, checklist, alerts, event log, badges |

## Everything else

| Path | What |
| --- | --- |
| `backend/tests/` | 110 tests, including a network-blocking plugin |
| `frontend/e2e/` | Playwright specs that drive the delivered app and capture the screenshots |
| `scripts/` | Fixture generator, TypeScript generator |
| `samples/` | Bundled demo footage and the recording guide |
| `data/` | Runtime media and records. Gitignored |
| `run.py` | One-command start for all three platforms |
