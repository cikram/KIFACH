# Source layout and handoff seams

The backend files are real Python source with empty functions. The frontend is a React shell whose components render nothing yet. Python, React, and the minimal Vite development runner are the only current tooling choices; no web API framework, model, storage, or final schema has been selected.

| Workstream | Files | Responsibility |
| --- | --- | --- |
| Shared shapes | `backend/app/domain/models.py` | Replace placeholder types once adjacent workstreams agree on fields. |
| Domain | `backend/app/domain/skill_graph.py`, `verifier.py` | Review and validate procedures; assess learner observations. |
| Services | `backend/app/services/video.py`, `observation_extractor.py`, `skill_compiler.py` | Accept media, extract observations, draft procedures, and locate evidence. |
| API surface | `backend/app/api/skills.py`, `runs.py` | Entry points for teach, review, and practice. No transport is chosen yet. |
| Entry point | `backend/app/main.py` | Placeholder for assembling the backend when a server approach is chosen. |
| Prompts | `backend/app/prompts/` | Reserved for prompts after the perception approach is tested. |
| React experience | `frontend/src/App.jsx`, `frontend/src/components/` | Provide entry points for capture, review, practice, feedback, and evidence. |

Before implementing a seam, agree on its data shape and ownership with adjacent workstreams. Rename or replace the stubs as the first end-to-end slice clarifies the design.
