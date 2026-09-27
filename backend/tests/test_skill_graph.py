"""Procedure validation, the bounded repair pass, review, and publication."""

from __future__ import annotations

from app.domain.models import (
    GraphProposal,
    OrderingRule,
    SkillGraph,
    SkillStatus,
    Step,
)
from app.domain.skill_graph import (
    MAX_STEPS,
    apply_review,
    dependency_edges,
    find_cycle,
    publish,
    repair_proposal,
    topological_order,
    validate_procedure,
)


def step(step_id: str, **kwargs) -> Step:
    defaults = {
        "title": step_id.replace("_", " ").title(),
        "checkpoint": f"{step_id} is visibly done",
    }
    defaults.update(kwargs)
    return Step(step_id=step_id, **defaults)


def graph(**kwargs) -> SkillGraph:
    defaults = {
        "skill_id": "skill_1",
        "title": "Reference",
        "steps": [step("a"), step("b", depends_on=["a"]), step("c", depends_on=["b"])],
        "rules": [],
    }
    defaults.update(kwargs)
    return SkillGraph(**defaults)


def test_a_sound_procedure_validates():
    assert validate_procedure(graph()).ok


def test_too_few_steps_is_reported():
    result = validate_procedure(graph(steps=[step("a")]))
    assert not result.ok
    assert any(issue.code == "too_few_steps" for issue in result.issues)


def test_too_many_steps_is_reported():
    steps = [step(f"s{i}") for i in range(MAX_STEPS + 2)]
    result = validate_procedure(graph(steps=steps))
    assert any(issue.code == "too_many_steps" for issue in result.issues)


def test_duplicate_ids_and_empty_titles_are_reported():
    result = validate_procedure(
        graph(steps=[step("a"), step("a"), Step(step_id="b", title=" ")])
    )
    codes = {issue.code for issue in result.issues}
    assert "step_id_duplicate" in codes
    assert "step_title_empty" in codes


def test_dangling_references_are_reported():
    result = validate_procedure(
        graph(
            steps=[step("a"), step("b", depends_on=["ghost"])],
            rules=[
                OrderingRule(rule_id="r1", before="a", after="phantom", reason="why")
            ],
        )
    )
    codes = {issue.code for issue in result.issues}
    assert "unknown_dependency" in codes
    assert "unknown_rule_step" in codes


def test_a_rule_without_a_reason_is_reported():
    result = validate_procedure(
        graph(rules=[OrderingRule(rule_id="r1", before="a", after="b", reason="  ")])
    )
    assert any(issue.code == "rule_reason_empty" for issue in result.issues)


def test_self_dependency_is_reported():
    result = validate_procedure(graph(steps=[step("a", depends_on=["a"]), step("b")]))
    assert any(issue.code == "self_dependency" for issue in result.issues)


def test_a_cycle_is_named_in_human_terms():
    cyclic = graph(
        steps=[
            step("a", title="Seat the LED", depends_on=["c"]),
            step("b", title="Add the resistor", depends_on=["a"]),
            step("c", title="Apply power", depends_on=["b"]),
        ]
    )
    result = validate_procedure(cyclic)
    message = next(i.message for i in result.issues if i.code == "cycle")
    assert "Seat the LED" in message
    assert "Apply power" in message
    assert "Remove one dependency or rule" in message


def test_rules_and_dependencies_share_one_edge_set():
    combined = graph(
        rules=[OrderingRule(rule_id="r1", before="c", after="a", reason="loops back")]
    )
    edges = dependency_edges(combined)
    assert ("c", "a") in edges
    assert find_cycle(edges, ["a", "b", "c"])


def test_topological_order_is_deterministic():
    ordered = graph(
        steps=[step("a"), step("b", depends_on=["a"]), step("c", depends_on=["a"])]
    )
    assert topological_order(ordered) == ["a", "b", "c"]
    assert topological_order(ordered) == topological_order(ordered)


def test_repair_drops_invented_references_and_duplicate_ids():
    proposal = GraphProposal(
        title="Draft",
        steps=[
            Step(step_id="a", title="A", checkpoint="a"),
            Step(step_id="a", title="Also A", checkpoint="a2"),
            Step(step_id="", title="Nameless", checkpoint="c"),
            Step(step_id="d", title="D", depends_on=["ghost", "d"], checkpoint="d"),
        ],
        rules=[
            OrderingRule(rule_id="r1", before="a", after="phantom", reason="invented"),
            OrderingRule(rule_id="r2", before="a", after="d", reason="fine"),
        ],
    )
    repaired = repair_proposal(proposal, validate_procedure(graph()).issues)
    ids = [item.step_id for item in repaired.steps]
    assert len(ids) == len(set(ids)), "ids are made unique"
    assert all(item.step_id for item in repaired.steps)
    assert repaired.steps[-1].depends_on == [], "invented and self references are dropped"
    assert [rule.rule_id for rule in repaired.rules] == ["r2"]


def test_repair_refuses_a_rule_that_would_close_a_cycle():
    proposal = GraphProposal(
        title="Draft",
        steps=[
            Step(step_id="a", title="A", checkpoint="a"),
            Step(step_id="b", title="B", depends_on=["a"], checkpoint="b"),
        ],
        rules=[OrderingRule(rule_id="r1", before="b", after="a", reason="contradicts")],
    )
    repaired = repair_proposal(proposal, [])
    assert repaired.rules == [], "a rule that contradicts a dependency is dropped"
    assert validate_procedure(
        SkillGraph(skill_id="s", title="t", steps=repaired.steps, rules=repaired.rules)
    ).ok
    assert not find_cycle(
        [(d, s.step_id) for s in repaired.steps for d in s.depends_on],
        [s.step_id for s in repaired.steps],
    )


def test_publishing_requires_confirmed_rules_and_checkpoints():
    draft = graph(
        rules=[OrderingRule(rule_id="r1", before="a", after="c", reason="safety")]
    )
    published, result = publish(draft)
    assert published is None
    assert any(issue.code == "rules_unconfirmed" for issue in result.issues)

    no_checkpoint = graph(steps=[step("a", checkpoint=""), step("b"), step("c")])
    published, result = publish(no_checkpoint)
    assert published is None
    assert any(issue.code == "checkpoint_missing" for issue in result.issues)


def test_publishing_a_reviewed_procedure_succeeds():
    reviewed = apply_review(
        graph(rules=[OrderingRule(rule_id="r1", before="a", after="c", reason="safety")]),
        confirmed_rule_ids=["r1"],
        mark_reviewed=True,
        reviewer_note="Looks right.",
    )
    assert reviewed.rules[0].confirmed_by_expert is True
    assert reviewed.review.reviewed is True
    assert reviewed.review.reviewer_note == "Looks right."

    published, result = publish(reviewed)
    assert result.ok
    assert published is not None
    assert published.status is SkillStatus.PUBLISHED
    assert published.review.reviewed_at is not None


def test_review_records_which_steps_a_human_touched():
    draft = graph()
    edited = [
        draft.steps[0].model_copy(update={"title": "Seat the LED properly"}),
        *draft.steps[1:],
    ]
    reviewed = apply_review(draft, steps=edited)
    assert reviewed.steps[0].proposed_by_model is False
    assert reviewed.steps[1].proposed_by_model is True
    assert reviewed.review.edited_steps == ["a"]


def test_review_keeps_previous_confirmations():
    draft = graph(
        rules=[
            OrderingRule(rule_id="r1", before="a", after="b", reason="one"),
            OrderingRule(rule_id="r2", before="b", after="c", reason="two"),
        ]
    )
    once = apply_review(draft, confirmed_rule_ids=["r1"])
    twice = apply_review(once, confirmed_rule_ids=["r2"])
    assert {rule.rule_id for rule in twice.rules if rule.confirmed_by_expert} == {
        "r1",
        "r2",
    }
