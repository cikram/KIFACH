"""Build, validate, and review procedures.

Ordering rules and step dependencies are two views of one constraint: a rule
that says B comes after A contributes the same edge as a dependency of B on A.
Validation therefore builds one edge set and reports a cycle in terms of the
step titles a user can actually edit.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from app.domain.models import (
    GraphProposal,
    OrderingRule,
    ReviewInfo,
    SkillGraph,
    SkillStatus,
    Step,
    ValidationIssue,
    ValidationResult,
)

MIN_STEPS = 2
MAX_STEPS = 8


def dependency_edges(graph: SkillGraph) -> list[tuple[str, str]]:
    """All before -> after edges implied by dependencies and ordering rules."""
    edges: list[tuple[str, str]] = []
    for step in graph.steps:
        for dep in step.depends_on:
            edges.append((dep, step.step_id))
    for rule in graph.rules:
        edges.append((rule.before, rule.after))
    return edges


def find_cycle(edges: list[tuple[str, str]], nodes: list[str]) -> list[str]:
    """Return one cycle as a node path, or an empty list when acyclic."""
    successors: dict[str, list[str]] = defaultdict(list)
    for before, after in edges:
        successors[before].append(after)

    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in nodes}
    path: list[str] = []

    def visit(node: str) -> list[str]:
        color[node] = GREY
        path.append(node)
        for nxt in successors.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == GREY:
                start = path.index(nxt)
                return path[start:] + [nxt]
            if color[nxt] == WHITE:
                found = visit(nxt)
                if found:
                    return found
        path.pop()
        color[node] = BLACK
        return []

    for node in nodes:
        if color.get(node) == WHITE:
            found = visit(node)
            if found:
                return found
    return []


def topological_order(graph: SkillGraph) -> list[str]:
    """Deterministic topological order: ties break on the declared step order."""
    position = {step.step_id: i for i, step in enumerate(graph.steps)}
    edges = [
        (b, a)
        for b, a in dependency_edges(graph)
        if b in position and a in position
    ]
    indegree = {step_id: 0 for step_id in position}
    successors: dict[str, list[str]] = defaultdict(list)
    for before, after in edges:
        successors[before].append(after)
        indegree[after] += 1

    ready = sorted([s for s, d in indegree.items() if d == 0], key=lambda s: position[s])
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for nxt in successors.get(node, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
                ready.sort(key=lambda s: position[s])
    return order


def validate_procedure(graph: SkillGraph) -> ValidationResult:
    """Structural validation. Every issue names something a human can fix."""
    issues: list[ValidationIssue] = []

    if not graph.title.strip():
        issues.append(
            ValidationIssue(code="title_empty", message="The procedure needs a title.")
        )

    step_ids = [step.step_id for step in graph.steps]
    if len(graph.steps) < MIN_STEPS:
        issues.append(
            ValidationIssue(
                code="too_few_steps",
                message=(
                    f"A procedure needs at least {MIN_STEPS} steps; "
                    f"this one has {len(graph.steps)}."
                ),
            )
        )
    if len(graph.steps) > MAX_STEPS:
        issues.append(
            ValidationIssue(
                code="too_many_steps",
                message=(
                    f"A procedure may have at most {MAX_STEPS} steps; "
                    f"this one has {len(graph.steps)}. Merge or remove steps."
                ),
            )
        )

    seen: set[str] = set()
    for step in graph.steps:
        if not step.step_id.strip():
            issues.append(
                ValidationIssue(code="step_id_empty", message="A step has no id.")
            )
        elif step.step_id in seen:
            issues.append(
                ValidationIssue(
                    code="step_id_duplicate",
                    step_id=step.step_id,
                    message=f"Two steps share the id {step.step_id}.",
                )
            )
        seen.add(step.step_id)

        if not step.title.strip():
            issues.append(
                ValidationIssue(
                    code="step_title_empty",
                    step_id=step.step_id,
                    message=f"Step {step.step_id} has an empty title.",
                )
            )
        if step.step_id in step.depends_on:
            issues.append(
                ValidationIssue(
                    code="self_dependency",
                    step_id=step.step_id,
                    message=f"Step {step.step_id} depends on itself.",
                )
            )
        for dep in step.depends_on:
            if dep not in step_ids:
                issues.append(
                    ValidationIssue(
                        code="unknown_dependency",
                        step_id=step.step_id,
                        message=(
                            f"Step {step.step_id} depends on {dep}, which is not a "
                            "step in this procedure."
                        ),
                    )
                )

    rule_ids: set[str] = set()
    for rule in graph.rules:
        if rule.rule_id in rule_ids:
            issues.append(
                ValidationIssue(
                    code="rule_id_duplicate",
                    rule_id=rule.rule_id,
                    message=f"Two rules share the id {rule.rule_id}.",
                )
            )
        rule_ids.add(rule.rule_id)
        for ref, label in ((rule.before, "before"), (rule.after, "after")):
            if ref not in step_ids:
                issues.append(
                    ValidationIssue(
                        code="unknown_rule_step",
                        rule_id=rule.rule_id,
                        message=(
                            f"Rule {rule.rule_id} names {ref} as its {label} step, "
                            "which is not a step in this procedure."
                        ),
                    )
                )
        if rule.before == rule.after:
            issues.append(
                ValidationIssue(
                    code="rule_self_reference",
                    rule_id=rule.rule_id,
                    message=f"Rule {rule.rule_id} orders a step against itself.",
                )
            )
        if not rule.reason.strip():
            issues.append(
                ValidationIssue(
                    code="rule_reason_empty",
                    rule_id=rule.rule_id,
                    message=f"Rule {rule.rule_id} needs a reason a reviewer can judge.",
                )
            )

    titles = {step.step_id: step.title or step.step_id for step in graph.steps}
    cycle = find_cycle(
        [(b, a) for b, a in dependency_edges(graph) if b in titles and a in titles],
        step_ids,
    )
    if cycle:
        readable = " then ".join(titles.get(node, node) for node in cycle)
        issues.append(
            ValidationIssue(
                code="cycle",
                message=(
                    "These steps require each other in a loop, so no order can "
                    f"satisfy them: {readable}. Remove one dependency or rule."
                ),
            )
        )

    return ValidationResult(ok=not issues, issues=issues)


def repair_proposal(
    proposal: GraphProposal, issues: list[ValidationIssue]
) -> GraphProposal:
    """One bounded, mechanical repair pass over a model proposal.

    This drops references the model invented and de-duplicates ids. It never
    invents steps and never removes a rule that is merely unconfirmed, so a
    proposal that stays invalid is saved as a flagged draft instead.
    """
    steps: list[Step] = []
    seen: set[str] = set()
    for index, step in enumerate(proposal.steps):
        step_id = step.step_id.strip() or f"step_{index + 1}"
        while step_id in seen:
            step_id = f"{step_id}_{index + 1}"
        seen.add(step_id)
        steps.append(step.model_copy(update={"step_id": step_id}))

    valid_ids = {step.step_id for step in steps}
    steps = [
        step.model_copy(
            update={
                "depends_on": [
                    dep
                    for dep in step.depends_on
                    if dep in valid_ids and dep != step.step_id
                ],
                "title": step.title.strip() or step.step_id,
            }
        )
        for step in steps
    ]

    rules: list[OrderingRule] = []
    rule_ids: set[str] = set()
    for index, rule in enumerate(proposal.rules):
        if rule.before not in valid_ids or rule.after not in valid_ids:
            continue
        if rule.before == rule.after:
            continue
        rule_id = rule.rule_id.strip() or f"rule_{index + 1}"
        while rule_id in rule_ids:
            rule_id = f"{rule_id}_{index + 1}"
        rule_ids.add(rule_id)
        reason = rule.reason.strip() or "Proposed by the model without a stated reason."
        rules.append(rule.model_copy(update={"rule_id": rule_id, "reason": reason}))

    # Drop the rule edges that close a cycle, keeping the earlier ones.
    kept: list[OrderingRule] = []
    node_ids = list(valid_ids)
    base_edges = [(d, s.step_id) for s in steps for d in s.depends_on]
    for rule in rules:
        candidate = base_edges + [(r.before, r.after) for r in kept]
        candidate.append((rule.before, rule.after))
        if find_cycle(candidate, node_ids):
            continue
        kept.append(rule)

    return proposal.model_copy(update={"steps": steps, "rules": kept})


def apply_review(
    draft: SkillGraph,
    *,
    steps: list[Step] | None = None,
    rules: list[OrderingRule] | None = None,
    title: str | None = None,
    summary: str | None = None,
    objects: list[str] | None = None,
    confirmed_rule_ids: list[str] | None = None,
    reviewer_note: str | None = None,
    mark_reviewed: bool = False,
) -> SkillGraph:
    """Return the draft with the expert's edits applied.

    Any step or rule whose content the expert changed loses its
    proposed_by_model flag, so the UI can keep showing what is still only a
    model proposal.
    """
    original_steps = {step.step_id: step for step in draft.steps}
    new_steps = list(steps) if steps is not None else list(draft.steps)
    edited: list[str] = list(draft.review.edited_steps)
    reconciled: list[Step] = []
    for step in new_steps:
        previous = original_steps.get(step.step_id)
        changed = previous is None or previous.model_dump() != step.model_dump()
        if changed:
            if step.step_id not in edited:
                edited.append(step.step_id)
            step = step.model_copy(update={"proposed_by_model": False})
        reconciled.append(step)

    new_rules = list(rules) if rules is not None else list(draft.rules)
    confirmed = list(draft.review.confirmed_rules)
    if confirmed_rule_ids:
        for rule_id in confirmed_rule_ids:
            if rule_id not in confirmed:
                confirmed.append(rule_id)
    reconciled_rules = [
        rule.model_copy(update={"confirmed_by_expert": True})
        if rule.rule_id in confirmed
        else rule
        for rule in new_rules
    ]

    review = ReviewInfo(
        reviewed=mark_reviewed or draft.review.reviewed,
        reviewed_at=(
            datetime.now(timezone.utc)
            if mark_reviewed
            else draft.review.reviewed_at
        ),
        edited_steps=edited,
        confirmed_rules=[r.rule_id for r in reconciled_rules if r.confirmed_by_expert],
        reviewer_note=(
            reviewer_note if reviewer_note is not None else draft.review.reviewer_note
        ),
    )

    return draft.model_copy(
        update={
            "title": title if title is not None else draft.title,
            "summary": summary if summary is not None else draft.summary,
            "objects": objects if objects is not None else draft.objects,
            "steps": reconciled,
            "rules": reconciled_rules,
            "review": review,
            "updated_at": datetime.now(timezone.utc),
        }
    )


def publish(graph: SkillGraph) -> tuple[SkillGraph | None, ValidationResult]:
    """Validate and publish. Unconfirmed rules block publication."""
    result = validate_procedure(graph)
    issues = list(result.issues)

    unconfirmed = [r.rule_id for r in graph.rules if not r.confirmed_by_expert]
    if unconfirmed:
        issues.append(
            ValidationIssue(
                code="rules_unconfirmed",
                rule_id=unconfirmed[0],
                message=(
                    "Confirm or remove every proposed ordering and safety rule "
                    f"before publishing: {', '.join(unconfirmed)}."
                ),
            )
        )

    missing_checkpoints = [
        step.step_id for step in graph.steps if not step.checkpoint.strip()
    ]
    if missing_checkpoints:
        issues.append(
            ValidationIssue(
                code="checkpoint_missing",
                step_id=missing_checkpoints[0],
                message=(
                    "Every step needs a visible checkpoint before publishing. "
                    f"Missing: {', '.join(missing_checkpoints)}."
                ),
            )
        )

    if issues:
        return None, ValidationResult(ok=False, issues=issues)

    published = graph.model_copy(
        update={
            "status": SkillStatus.PUBLISHED,
            "validation_flags": [],
            "updated_at": datetime.now(timezone.utc),
            "review": graph.review.model_copy(
                update={
                    "reviewed": True,
                    "reviewed_at": graph.review.reviewed_at
                    or datetime.now(timezone.utc),
                }
            ),
        }
    )
    return published, ValidationResult(ok=True, issues=[])
