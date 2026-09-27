# KIFACH build report

Build date: 2026-09-27. Platform verified on: Windows 11, Python 3.13.12,
Node 22.23.3.

## 1. Delivery status

| Area | State |
| --- | --- |
| Teach → review → publish → practice → verdict → correction | Working end to end |
| Deterministic engine and replay | Working, 96% line coverage, replay proven identical |
| Offline Demo Mode | Working, labelled MOCK on every screen |
| Live camera mode (WebSocket) | Implemented; protocol tested with synthetic frames. **Not tested with a real camera** |
| NVIDIA / OpenAI-compatible provider | Implemented and tested offline against a stub transport. **Never run against a live endpoint — no credentials were available** |
| Cached replay mode | Working; proven to make no network calls |
| Real recorded footage | **Not produced.** All bundled clips are drawn fixtures |
| Backend tests | 110 passed, 92% total coverage |
| Frontend typecheck / lint / unit tests / build | All pass, 24 unit tests |
| End-to-end (Playwright, headless) | 3 specs pass, covering the full loop and all five verdict cases |
| One-command production start | Working: `python run.py` serves the API and the built UI on :8000 |

The single honest gap is perception: everything around the model is built and
tested, and the model path itself has never spoken to a real model in this
build. Section 5 says exactly what that means.

## 2. Architecture and the decisions behind it

**The model observes; the reviewed procedure and deterministic code decide.**
Everything else follows from that.

| Decision | Reason |
| --- | --- |
| Pure-Python engine: no network, disk, clock, or randomness | Makes `POST /api/attempts/{id}/replay` meaningful — identical inputs must give an identical event log and verdict, which the UI and tests check |
| Three verdicts, not two | A hackathon demo that says NOT VERIFIED when a hand covered the work is worse than useless. `INCONCLUSIVE` is a first-class outcome |
| `absent` ≠ "not observed" | Only an explicit absence observation, made while the checkpoint area was visible, can support a claim that a step was skipped. Missing evidence keeps the assessment inconclusive |
| Publication requires human confirmation of every proposed rule | A model-proposed safety rule that nobody read is not a standard to judge a learner against. `POST /publish` refuses until each rule is confirmed or removed |
| Ordering rules and dependencies share one edge set | A rule "B after A" is the same constraint as a dependency; validating them together is what catches a cycle a reviewer introduced by hand |
| Overlapping windows, with an independence rule | Overlap means one event is often described twice. `independent_gap_s` stops two reports of one event from counting as two confirmations; live mode requires two independent confirmations, upload mode one |
| Engine re-run after each window instead of incremental state | Streaming and replay then execute the same code, so the progress a user watched and the stored verdict cannot diverge |
| Correction requires undo → prerequisite → redo | Seeing the resistor later does not undo having powered the board without it. The alert state machine requires the full sequence before it resolves |
| JSON files under `data/`, atomic writes | Prototype storage that survives an interrupted run; a truncated record is never left behind |
| Frontend types generated from Pydantic models | `python scripts/gen_types.py --check` runs in the test suite, so a backend field rename cannot silently break the UI |
| WebM/VP8 fixtures rather than MP4 | See section 4 — the first fixtures were unplayable in the browser |
| Custom 40-line hash router instead of a routing library | Six screens, no nested routes; keeps the dependency list to what the brief specified |

## 3. Phase notes

**Contract first.** `backend/app/domain/models.py` was written before anything
else, and the TypeScript generator was added immediately, so the API shape was
fixed while both sides were still cheap to change.

**Vertical slice.** Media → frames → mock windows → proposal → validation →
draft, then review → publish → observe → engine → verdict. The first full run of
all five scenarios produced the intended verdicts without engine changes, which
suggests the state machine was specified correctly before it was coded.

**Provider layer.** Written against the documented OpenAI-compatible shape, then
tested with `httpx.MockTransport`: retries, JSON repair, fence stripping, image
reduction, caching, and the rule that a model may not mark its own rules as
expert-confirmed.

**UI.** React + TypeScript strict, Tailwind with CSS-variable theming, dagre
layout for the procedure graph. Screenshots were inspected, and three real
defects came out of that inspection (section 4).

**Hardening.** Full suites, a network-blocked test run, a replay-mode run, a
clean production start, and a browser-console assertion inside the e2e suite.

## 4. Problems found and fixed

1. **The sample videos would not play in the browser.** OpenCV's `mp4v` writer
   produces MPEG-4 Part 2, which Chrome cannot decode, so the evidence player
   stayed blank and clicking evidence seeked nothing. OpenCV here cannot write
   H.264 (`avc1`/`H264` both fail without the OpenH264 DLL). Fixed by writing
   VP8 in WebM, which OpenCV both writes and reads and every target browser
   plays. Caught by the Playwright assertion that the video position changes
   after an evidence click.
2. **A false limitation on every attempt.** The frame extractor treated a
   container timestamp of `0` as "no timestamp available", so every video
   reported "evidence times were derived from the frame rate and may drift" —
   an honest-sounding warning that was itself false. Now only a later frame
   still reporting nothing triggers the fallback.
3. **A blurred header.** A typo (`backdrop blur` instead of `backdrop-blur`)
   applied Tailwind's blur filter to the whole header. Visible only by looking
   at the screenshots.
4. **FastAPI refused to start once the frontend was built.** The SPA catch-all
   was annotated `FileResponse | JSONResponse`, which FastAPI tried to turn into
   a response model. Only reproduced after `frontend/dist` existed, which is why
   the production start-up smoke test matters.
5. **`proposed` badges on a published graph.** Steps a reviewer never edited kept
   `proposed_by_model`, so a published procedure still showed "proposed". The
   graph now shows that only while the skill is a draft.
6. **SSE disconnects spammed the console.** Windows logs a `ConnectionResetError`
   whenever a browser closes an SSE stream; `run.py` filters that specific noise
   so a demo terminal stays readable.

## 5. Provider findings, and what was and was not tested

**Model id.** NVIDIA's live catalogue at `GET
https://integrate.api.nvidia.com/v1/models` (queried 2026-09-27, 82 models)
lists `nvidia/cosmos-reason2-8b`, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`,
`microsoft/phi-3-vision-128k-instruct`, and `nvidia/vila`. The default is
`nvidia/cosmos-reason2-8b`: it is the physical-reasoning VLM in that catalogue
and matches the task.

**Image input format.** NVIDIA's VLM NIM documentation for Cosmos Reason2
([docs.nvidia.com](https://docs.nvidia.com/nim/vision-language-models/1.6.0/examples/cosmos-reason2/api.html))
documents `POST /v1/chat/completions` with image parts of the form
`{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`,
supported formats JPG/JPEG/PNG, and a public-URL form as an alternative. That
page documents **no** maximum image count or payload size, so KIFACH sends
`KIFACH_MAX_IMAGES_PER_CALL` (default 4) JPEG frames per call and halves that
count if the endpoint answers 400/413/422, recording the change in the provider's
notes. KIFACH's own frames are ~768 px JPEGs at quality 85, which keeps a
four-image request comfortably small.

**What was tested.** The whole provider mechanism, offline, with
`httpx.MockTransport` standing in for the endpoint
(`backend/tests/test_http_provider.py`, 10 tests): request shape and model id,
base64 data-URI image parts, temperature 0, fenced-JSON recovery, one bounded
repair re-ask, retry with backoff on 429/503, a reportable error after exhausting
retries, image-count reduction on a rejected payload, cache hit on a repeated
request, validation and filtering of learner observations (an unknown status
becomes `uncertain`, an unknown step id is dropped), the rule that a model cannot
confirm its own rules, and that the API key never appears in health output.

**What was NOT tested.** No request has ever been sent to `integrate.api.nvidia.com`
or any other model endpoint from this build. No API key was available. Therefore:

- No claim is made about this model's accuracy on breadboard footage.
- No cached genuine response exists in the repository, so `KIFACH_CACHE=replay`
  currently has nothing to replay and correctly reports that.
- Every observation in every screenshot, test, and demo in this repository is
  `MOCK`: scripted output from `backend/app/providers/scenarios.py`.

To run the real path: `NVIDIA_API_KEY=nvapi-... python run.py`, teach from real
footage, and read the provider badge. It will say `LIVE`.

## 6. Footage: what is real and what is drawn

| Kind | In this build |
| --- | --- |
| Real recorded footage | **None.** No camera session was possible |
| Synthetic fixtures | Six WebM clips drawn by `scripts/make_synthetic_video.py`: expert, correct, alternate_order, wrong_order, uncertain, corrected |
| Mock observations | Scripted per scenario, timed to match the fixtures |
| Cached genuine model responses | **None** |
| Live model responses | **None** |

The fixtures are deliberately legible: a breadboard, an LED that lights, a
resistor that is either present or visibly absent, a ground wire, a battery pack,
and a hand that occludes the work in the uncertain scenario. They prove the
engine and the product loop. They prove nothing about perception.

## 7. Test results

All commands were run from the repository root on 2026-09-27.

| Command | Result |
| --- | --- |
| `python -m pytest backend/tests -q` | **110 passed** |
| `python -m pytest backend/tests --cov=app` | **92% total**; engine `verifier.py` 96%, `models.py` 99%, `http_vlm.py` 87%, `mock.py` 91%, `skill_graph.py` 96% |
| `python -m pytest backend/tests -q -p tests.no_network` | **110 passed** with all non-loopback sockets blocked |
| `python scripts/gen_types.py --check` | Frontend types match the backend models |
| `npm --prefix frontend run typecheck` | Clean (TypeScript strict, no `any`) |
| `npm --prefix frontend run lint` | Clean, 0 errors, 0 warnings |
| `npm --prefix frontend test` | **24 passed** (3 files) |
| `npm --prefix frontend run build` | Built; 563 kB JS (182 kB gzipped), 31 kB CSS |
| `npm --prefix frontend run e2e` | **3 passed** headless, including a console-error assertion on every page |
| `python run.py --port 8200` + HTTP smoke | `/api/health` ok, `/` 200, `/docs` 200, `/samples/expert.webm` 200 |
| Replay-mode smoke (no network, fake key) | Job fails with: "No cached response for expert_window and replay mode makes no network calls." Nothing fabricated |

The single warning in the backend run is Starlette telling us `TestClient` prefers
`httpx2`; it does not affect behaviour.

**Engine coverage detail.** The 21 engine tests cover: a correct run, a valid
alternate topological order, a supported wrong order, missing evidence vs.
explicit absence, uncertain and low-confidence evidence, the full correction
sequence, a redo attempted before correction, duplicate and overlapping-window
observations, the live confirmation requirement, undo with dependents, undo of a
step that was never done, a missing required step at the end, an absent required
step at the end, optional steps, unknown step ids, cycle rejection (including a
rule that closes a cycle), byte-identical replay, and 25 random valid topological
orders under a fixed seed.

**End-to-end coverage.** Teach from the expert sample → the streamed window
analysis → a refused publish before review → confirming the safety rule →
publish → a correct attempt (VERIFIED) → replay reproducing it → a wrong-order
attempt (NOT VERIFIED) with an evidence click that moves the video position → an
obscured attempt (INCONCLUSIVE, and asserted *not* NOT_VERIFIED) → a corrected
attempt (VERIFIED, with "corrected" in its reasons) → an alternate valid order
(VERIFIED) → Demo Mode labelled MOCK → phone width with no horizontal overflow.

## 8. Demo risks and mitigations

| Risk | Mitigation |
| --- | --- |
| No network or no credentials at the venue | Demo Mode is the default and needs neither. Everything is labelled MOCK, so nothing is misrepresented |
| A judge uploads their own video in mock mode | The mock refuses with an actionable message rather than inventing an assessment. Say this out loud — it is the point |
| Live camera fails | Upload mode is the primary path; the live screen states its requirements up front |
| Port 8000 taken | `python run.py --port 8123` |
| Stale data from a rehearsal | Delete `data/` before the demo; the library starts empty |
| Someone asks "is the model deciding?" | Open the engine event log and the replay button; both are on the verdict screen |

## 9. The 90-second demo

Setup: `python run.py`, browser at `http://127.0.0.1:8000`, `data/` deleted, one
tab.

| Time | Click | Say |
| --- | --- | --- |
| 0:00 | Home screen | "An expert shows a task once. KIFACH turns it into a procedure a learner can be checked against — and every check is inspectable." |
| 0:08 | **Teach a skill** → the **Expert demonstration** sample → **Derive the procedure** | "It samples frames with their real timestamps and describes each four-second window. Notice it also records what it could not see." |
| 0:25 | **Review the draft** | "This is a draft, not a procedure. The model proposed a safety rule: resistor before power." |
| 0:32 | **Publish procedure** (it refuses) | "It will not publish until a human confirms that rule. The model does not get to set the standard." |
| 0:40 | **Confirm rule** → **Publish procedure** | "Now it is a published procedure." |
| 0:48 | **Practice this skill** → the **Wrong order** sample | "A learner applies power before fitting the resistor." |
| 1:00 | Point at the verdict | "NOT VERIFIED — and here is why, in the reviewed procedure's own words." |
| 1:06 | Click the alert timestamp | "Every claim seeks the footage it rests on." |
| 1:14 | **Replay the engine** | "Same observations, same verdict, every time. The model observed; deterministic code decided." |
| 1:22 | Back → Practice → **Obscured attempt** | "And when a hand covers the work, it says inconclusive rather than failing someone on a guess." |
| 1:30 | (If time) **Wrong order, then corrected** | "A correction only counts if power came off, the resistor went in, and power went back on." |

Closing line: "Show once. Teach forever — with evidence for every call it makes."

## 10. Submission assets

| Asset | Location |
| --- | --- |
| Running app | `python run.py` → <http://127.0.0.1:8000> |
| Wordmark | `docs/wordmark.svg` |
| Screenshots (10) | `docs/screenshots/` |
| Demo footage | `samples/*.webm` + `samples/scenarios.json` |
| Recording guide | `samples/RECORDING_GUIDE.md` |
| API docs | `/docs` on the running app |
| Test suites | `backend/tests/`, `frontend/src/**/*.test.ts(x)`, `frontend/e2e/` |
| Demo script | Section 9 above |
| Decisions and progress | `docs/brain/decisions.md`, `docs/brain/progress.md` |

## 11. Remaining work

1. **Run the NVIDIA path against real footage** and record, per step, where
   perception succeeds and fails. This is the only way to know whether the
   checkpoints in the reference procedure are observable in practice.
2. **Record the six real clips** in `samples/RECORDING_GUIDE.md` and re-validate
   against them.
3. **Checkpoint regions.** Letting the expert box the area a checkpoint applies
   to would make `absent` observations far more reliable than whole-frame
   judgement.
4. **A real camera test of live mode**, including permission denial, disconnects,
   and slow provider responses under load.
5. **SQLite instead of JSON files** once more than one person uses an instance.
