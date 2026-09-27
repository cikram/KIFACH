# Five-person build plan

Proposed for the 27 September 2026 hackathon. Assign names to the five owners at the next huddle. This plan divides work by files and observable deliverables. FastAPI is the chosen backend framework; the model, persistence format, and final schema remain open.

The [official event page](https://hackathon.gomycode.com/) calls for a working prototype, a 90-second demo video, a short project card, and AI/tool disclosures by **17:30 Tunis time**. Treat that as the deadline for the complete package, not the 20:00 event close.

| Owner                                     | Workstream and files                                                                                                         | Deliverable to show the team                                                                                                                                                                                                                                                 |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1 — AI and observations**               | `backend/app/services/observation_extractor.py`, `backend/app/prompts/`                                                      | Expert and learner recordings become timestamped observations. Test the chosen model or method on the actual demo footage; surface uncertainty and provide example outputs for integration.                                                                                  |
| **2 — Procedure and verification**        | `backend/app/domain/models.py`, `skill_graph.py`, `verifier.py`                                                              | Agree on the shared shapes with owners 1 and 5; validate a reviewed procedure; assess correct, skipped, wrong-order, and uncertain attempts without asking the model for the final verdict.                                                                                  |
| **3 — Video, evidence, and test footage** | `backend/app/services/video.py`; demo recordings and evaluation notes                                                        | Record one expert demo plus correct and incorrect learner attempts. Make media usable by owner 1 and ensure an assessment can jump to a relevant time or frame. Keep a small expected-versus-actual case list.                                                               |
| **4 — React experience**                  | `frontend/src/`                                                                                                              | A clear teach → review → practice → result flow. Build against agreed sample payloads first; the result view shows step state, a specific reason, and clickable evidence.                                                                                                    |
| **5 — Integration and submission**        | `backend/app/api/`, `backend/app/main.py`, `backend/app/services/skill_compiler.py`, run instructions and submission package | Connect the workstreams into one end-to-end demo, add the agreed product routes to FastAPI, maintain a runnable command, coordinate the 90-second video and project card, and check every submission link. The registered lead performs the final submission if required. |

## First shared agreement

Spend 15 minutes together on one **short, visible demo task** and one deliberate error. Owners 1, 2, 4, and 5 agree on the smallest exchanged shapes for **observation**, **reviewed procedure**, and **assessment**, including a source-media time reference and an uncertain result. Owner 3 records the first clips immediately. Keep the agreed example payloads in the repo so both sides can work before the live connection is ready.

## Integration checkpoints

| By        | Checkpoint                                                                                                                                                                                                                            |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **14:00** | Each owner can show their deliverable using the same sample task and agreed payloads. Owner 5 can run at least one full teach → result path, even if a still-unfinished module is temporarily fed a clearly identified sample output. |
| **15:30** | Connect actual observation output and show one correct and one incorrect attempt with evidence. Run the core failure cases.                                                                                                           |
| **16:30** | Freeze the demo path, rehearse it, and record the 90-second video. Fix only blockers after this point.                                                                                                                                |
| **17:00** | Project card, AI/tool disclosures, prototype link, and video link are ready and checked on another device. Submit before the official **17:30 Tunis** cutoff.                                                                         |

## Handoff rule

Each owner gives owner 5 a callable result, one representative input/output, a run command if needed, and one known limitation. If the model or camera fails, show the last genuine recorded result and label any sample data honestly. The demo must not imply that sample outputs came from live perception.
