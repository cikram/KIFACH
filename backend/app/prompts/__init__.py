"""Prompt texts and the schemas the model must answer with.

The prompt version is part of the response cache key, so editing a prompt
invalidates cached answers instead of silently mixing them.
"""

from __future__ import annotations

import json

from app.domain.models import Step

PROMPT_VERSION = "v1"

_JSON_RULES = (
    "Answer with one JSON object and nothing else. No prose, no markdown fences. "
    "Use only the keys described. Use an empty list when you have nothing to report."
)

OBSERVER_SYSTEM = (
    "You are a careful industrial video observer. You report only what is visible "
    "in the frames you are given. You never guess at an electrical connection, a "
    "hidden fastener, or anything behind a hand or a tool: if it is obscured, you "
    "say so in limitations instead of reporting it. You never judge whether the "
    "work was done correctly, in the right order, or safely. " + _JSON_RULES
)

WINDOW_SCHEMA = {
    "objects": ["short noun phrases for objects clearly visible"],
    "actions": ["short descriptions of hand or tool actions visible in this window"],
    "changes": ["state changes visible between the first and last frame"],
    "candidate_steps": ["short titles of task steps these frames could show completing"],
    "limitations": ["anything you could not see well, and why"],
}


def expert_window_prompt(
    *, t_start: float, t_end: float, frame_count: int, task_hint: str = ""
) -> str:
    hint = f"\nThe expert said the task is: {task_hint}\n" if task_hint else ""
    return (
        f"These {frame_count} frames are an expert demonstration between "
        f"{t_start:.2f}s and {t_end:.2f}s of one video, in order.{hint}\n"
        "Describe what is visible in this time window.\n\n"
        f"Answer with this JSON shape:\n{json.dumps(WINDOW_SCHEMA, indent=2)}"
    )


PROPOSAL_SYSTEM = (
    "You turn observations of one expert demonstration into a draft procedure that "
    "a human expert will review before it is used. Every step must be checkable by "
    "looking at a video: its checkpoint is what a reviewer would see once the step "
    "is done. Propose a dependency or an ordering rule only when the demonstration "
    "or physical necessity justifies it, and state the reason in plain language. "
    "Mark every rule as a proposal; you are not approving anything. " + _JSON_RULES
)

PROPOSAL_SCHEMA = {
    "title": "short task title",
    "summary": "one sentence describing the task",
    "objects": ["objects the task uses"],
    "steps": [
        {
            "step_id": "snake_case_id",
            "title": "short imperative title",
            "action": "the physical action",
            "objects": ["objects involved"],
            "description": "one or two sentences",
            "checkpoint": "what is visibly true once this step is done",
            "common_mistakes": ["what learners get wrong"],
            "required": True,
            "depends_on": ["step_ids that must be done first"],
        }
    ],
    "rules": [
        {
            "rule_id": "rule_1",
            "kind": "order or safety",
            "before": "step_id",
            "after": "step_id",
            "reason": "why this order matters",
        }
    ],
}


def proposal_prompt(*, windows_text: str, min_steps: int, max_steps: int) -> str:
    return (
        "Here are time-ordered observations of one expert demonstration:\n\n"
        f"{windows_text}\n\n"
        f"Propose a procedure with between {min_steps} and {max_steps} steps. Each "
        "step must be one atomic, visually checkable action. Do not invent steps "
        "that no observation supports.\n\n"
        f"Answer with this JSON shape:\n{json.dumps(PROPOSAL_SCHEMA, indent=2)}"
    )


LEARNER_SYSTEM = (
    "You observe a learner attempting a known procedure. For each step you are "
    "given, report only what these frames show about that step. Statuses: "
    "'completed' when the step's checkpoint is visibly satisfied in these frames; "
    "'in_progress' when the action is under way; "
    "'absent' ONLY when you can clearly see the place the checkpoint applies to and "
    "the expected result is not there; "
    "'uncertain' when you cannot tell, including when a hand, tool, or angle hides "
    "it. If a step is simply not shown in these frames, leave it out entirely — "
    "that is not the same as 'absent'. Never say whether the learner passed, "
    "failed, or worked in the wrong order. " + _JSON_RULES
)

OBSERVE_SCHEMA = {
    "observations": [
        {
            "step_id": "one of the given step ids",
            "status": "completed | in_progress | undone | absent | uncertain",
            "confidence": 0.0,
            "rationale": "what in these frames supports this, in one short sentence",
        }
    ],
    "limitations": ["anything that limited what you could see"],
}


def learner_window_prompt(
    *,
    t_start: float,
    t_end: float,
    frame_count: int,
    skill_title: str,
    steps: list[Step],
) -> str:
    lines = []
    for step in steps:
        checkpoint = step.checkpoint or "(no checkpoint recorded)"
        lines.append(f"- {step.step_id}: {step.title} — checkpoint: {checkpoint}")
    return (
        f"Procedure: {skill_title}\nSteps and their checkpoints:\n"
        + "\n".join(lines)
        + f"\n\nThese {frame_count} frames are a learner attempt between "
        f"{t_start:.2f}s and {t_end:.2f}s of one video, in order. Report what these "
        "frames show about those steps.\n\n"
        f"Answer with this JSON shape:\n{json.dumps(OBSERVE_SCHEMA, indent=2)}"
    )


def repair_prompt(*, errors: str) -> str:
    return (
        "Your previous answer did not match the required JSON shape. The validator "
        f"reported:\n{errors}\n\nAnswer again with one corrected JSON object only."
    )
