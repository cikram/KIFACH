# KIFACH project guidance

KIFACH is an 11-hour hackathon prototype: an expert demonstrates a physical task, the system derives a reviewable procedure, and a learner's attempt is assessed with evidence. Read [docs/README.md](docs/README.md) before changing the product shape.

## Working rules

- Keep the path from expert demonstration to learner feedback demoable end to end. Preserve timestamps or other evidence that lets a human inspect an assessment.
- Treat model observations as fallible. Keep observation, procedure construction, and assessment separate, and represent uncertainty when evidence is insufficient.
- Python backend and React frontend source files are empty starting points. Their names and signatures are collaboration aids, not a final API, storage format, or schema. See [docs/brain/components.md](docs/brain/components.md) when splitting work.
- Record confirmed product or technical decisions and their reasons in [docs/brain/decisions.md](docs/brain/decisions.md). Keep unresolved questions in [docs/README.md](docs/README.md) and proposals in [docs/brain/brainstorm.md](docs/brain/brainstorm.md). Update [docs/brain/progress.md](docs/brain/progress.md) after meaningful progress so a new session can resume quickly.
- When implementing a component, agree on the shared input and output shapes with adjacent workstreams before depending on them. Keep `README.md` aligned with each runnable path.

## Current state

This repository has source stubs and a blank frontend shell. There is no working prototype yet. `CLAUDE.md` points here.
