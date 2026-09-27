# KIFACH brain

Updated: 2026-09-27. This is the handoff entry point for new sessions.

## Product brief

The selected idea is **KIFACH — “Show once. Teach forever.”** An expert records a short physical demonstration. KIFACH identifies observable actions, builds a procedure that the expert can review, observes a learner's attempt, and explains completion or mistakes with time-linked evidence. The compelling demo loop is **teach → review procedure → attempt → inspect feedback → correct**.

The hackathon is GOMYCODE “Come Build with AI” in Morocco, in partnership with NVIDIA. The build window is 11 hours. Aim for one reliable, visual, short physical task rather than breadth.

## Source discussions

- [Selected idea](https://chatgpt.com/s/t_6ab8681fd3708191bd59df08fbd8efa2): product concept, demo sequence, and potential use cases.
- [Brainstorming](https://chatgpt.com/s/t_6ab8ee5bff448191a811c10e293ba46e): proposed architecture, model and computer-vision options, demo setup, edge cases, and possible team split. These are suggestions, not adopted decisions.

## Candidate shape from the discussions

Expert media → observations with time ranges → reviewable procedure with steps and dependencies → learner media → observations → assessment with evidence. A human should be able to inspect and amend the derived procedure. The assessor should distinguish supported completion, a specific violation, incomplete footage, and uncertain observation. Independent steps may allow more than one valid order.

The empty Python functions under [`backend/app/`](../../backend/app/) and React components under [`frontend/`](../../frontend/) expose seams for parallel work. Their [layout](components.md) is a starting point to discuss, not a fixed contract.

## Open decisions

- Which physical demo task and filming setup give reliable visible evidence?
- Which parts of the loop use live capture versus uploaded recordings for the first demo?
- What exact observation, procedure, and assessment schemas will the workstreams share?
- Which model endpoint or other perception method can the team actually access and validate during the event?
- What backend server, UI navigation, persistence, and deployment path fit the team and venue?
- How will correction be shown: continuation of an attempt, a new attempt, or both?

See [decisions.md](decisions.md) for confirmed choices and [progress.md](progress.md) for the latest checkpoint.
See [brainstorm.md](brainstorm.md) for promising approaches and demo cases that remain unchosen.
