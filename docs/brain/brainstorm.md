# Brainstorming to evaluate

These are proposals from the [brainstorming chat](https://chatgpt.com/s/t_6ab8ee5bff448191a811c10e293ba46e), not team decisions or verified vendor capabilities. Choose only after a quick experiment against actual demo footage.

## Possible technical split

- **Perception:** turn expert and learner footage into timestamped observations of visible objects, actions, and state changes. Keep confidence or uncertainty available.
- **Procedure:** derive steps, prerequisites, and expected outcomes from expert observations. Let the expert review and correct the result. A dependency graph can permit multiple valid step orders.
- **Verification:** compare learner observations with the reviewed procedure. Check prerequisites in software and return specific findings, including uncertainty when the footage does not support a conclusion.
- **Evidence and experience:** link each finding to a time or frame; show the video beside procedure progress and let the viewer jump to the evidence.
- **Integration:** connect the above into a teach and practice loop, preserve enough data for the demo, and test representative attempts.

The proposed separation is useful for diagnosing whether a bad result came from perception, procedure construction, or verification. The exact modules and data formats remain open.

## Candidate demo setups

- A short, highly visible assembly task with large, distinctive components and a deliberate out-of-order action.
- An LED and resistor setup was suggested in the selected idea. Small breadboard connections may be hard to see, so test the footage before choosing it.
- A simplified training jig with a module, connector, safety lock, and power connector was suggested as another option.
- Fiducial markers or conventional computer vision could help make object identity or position easier to observe if needed. They are optional, and using them would be a demo choice.

## Candidate perception options

The chat mentioned NVIDIA Cosmos 3 Nano Reasoner and Nemotron 3 Nano Omni, plus OpenCV/FFmpeg and optional markers. Treat names, access, input formats, structured output, latency, and cost as unverified until tested. Do not make the demo depend on a claimed capability before a small footage experiment succeeds.

## Minimum evaluation cases

Use a few short recorded attempts with expected outcomes: correct execution; skipped step; wrong order; different valid order; wrong object; repeated step; occluded action; incomplete recording. Decide how a correction is represented before claiming that a step can turn green afterward. Record actual outcomes and misses, including uncertain cases.

## Suggested demo story

Show an expert demonstration, the derived procedure and human review, a learner attempt with one visible mistake, a specific finding with time-linked evidence, and then a correction or corrected attempt. A polished evidence screen matters more than covering many tasks.
