"""Tests for the deterministic assessment engine.

These are the product's claims written as assertions: what counts as done, what
counts as a skip, what a correction must look like, and where the engine must
refuse to decide.
"""

from __future__ import annotations

import random

import pytest

from app.domain.models import (
    AlertKind,
    EngineConfig,
    EvidenceRef,
    Observation,
    ObservationStatus,
    OrderingRule,
    RuleKind,
    SkillGraph,
    SkillStatus,
    Step,
    StepState,
    Verdict,
)
from app.domain.skill_graph import validate_procedure
from app.domain.verifier import assess_attempt

VIDEO = "vid_test"


def evidence(t: float) -> EvidenceRef:
    return EvidenceRef(video_id=VIDEO, t_start=t, t_end=t + 1.0)


def observe(
    step_id: str,
    t: float,
    status: ObservationStatus = ObservationStatus.COMPLETED,
    confidence: float = 0.9,
    window: str | None = None,
) -> Observation:
    return Observation(
        observation_id=f"{step_id}@{t}:{status.value}",
        window_id=window or f"w{int(t)}",
        step_id=step_id,
        status=status,
        confidence=confidence,
        t_start=t,
        t_end=t + 1.0,
        evidence=evidence(t),
        rationale="test observation",
    )


@pytest.fixture
def graph() -> SkillGraph:
    """The reference LED procedure, already reviewed and published."""
    return SkillGraph(
        skill_id="skill_test",
        title="Light an LED",
        status=SkillStatus.PUBLISHED,
        steps=[
            Step(step_id="led", title="Seat the LED", checkpoint="LED in two rows"),
            Step(
                step_id="resistor",
                title="Connect the resistor",
                checkpoint="resistor bridges the rail",
                depends_on=["led"],
            ),
            Step(
                step_id="ground",
                title="Connect ground",
                checkpoint="black jumper on the blue rail",
                depends_on=["led"],
            ),
            Step(
                step_id="power",
                title="Apply power",
                checkpoint="battery lead on the red rail",
                depends_on=["ground"],
            ),
            Step(
                step_id="lit",
                title="Confirm the LED lights",
                checkpoint="the LED is lit",
                depends_on=["power"],
            ),
        ],
        rules=[
            OrderingRule(
                rule_id="r1",
                kind=RuleKind.SAFETY,
                before="resistor",
                after="power",
                reason="Without the resistor the LED takes the full supply current.",
                confirmed_by_expert=True,
            )
        ],
    )


def test_correct_run_is_verified(graph):
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("resistor", 6),
            observe("ground", 10),
            observe("power", 14),
            observe("lit", 18),
        ],
    )
    assert result.verdict is Verdict.VERIFIED
    assert all(state is StepState.DONE for state in result.step_states.values())
    assert result.alerts == []


def test_valid_alternate_order_is_verified(graph):
    """Ground before resistor breaks no rule: neither depends on the other."""
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("ground", 6),
            observe("resistor", 10),
            observe("power", 14),
            observe("lit", 18),
        ],
    )
    assert result.verdict is Verdict.VERIFIED


def test_supported_wrong_order_fails_with_evidence(graph):
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("ground", 6),
            observe("resistor", 9, status=ObservationStatus.ABSENT),
            observe("power", 10),
            observe("lit", 14),
        ],
    )
    assert result.verdict is Verdict.NOT_VERIFIED
    assert result.step_states["power"] is StepState.VIOLATION
    assert result.step_states["resistor"] is StepState.SKIPPED
    violation = next(a for a in result.alerts if a.kind is AlertKind.WRONG_ORDER)
    assert violation.supported is True
    assert violation.opened_at == 10
    assert violation.opened_evidence is not None
    assert "resistor" in violation.message.lower()


def test_missing_observation_is_not_absence(graph):
    """Never seeing the resistor cannot prove the learner skipped it."""
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("ground", 6),
            observe("power", 10),
            observe("lit", 14),
        ],
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.step_states["resistor"] is not StepState.SKIPPED
    assert all(not alert.supported for alert in result.alerts)
    assert any(a.kind is AlertKind.PREREQ_UNCONFIRMED for a in result.alerts)


def test_uncertain_observation_cannot_complete_a_step(graph):
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("resistor", 6, status=ObservationStatus.UNCERTAIN, confidence=0.35),
            observe("ground", 10),
            observe("power", 14),
            observe("lit", 18, status=ObservationStatus.UNCERTAIN, confidence=0.4),
        ],
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.step_states["resistor"] is StepState.UNCERTAIN
    assert result.step_states["lit"] is StepState.UNCERTAIN


def test_low_confidence_is_ignored_and_recorded(graph):
    result = assess_attempt(
        graph,
        [observe("led", 2, confidence=0.2)],
        EngineConfig(min_confidence=0.6),
    )
    ignored = [e for e in result.events if e.type.value == "low_confidence_ignored"]
    assert len(ignored) == 1
    assert result.step_states["led"] is StepState.UNCERTAIN
    assert result.verdict is Verdict.INCONCLUSIVE


def test_correction_sequence_resolves_the_violation(graph):
    """Undo the violating action, do the prerequisite, then redo it."""
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("ground", 6),
            observe("resistor", 9, status=ObservationStatus.ABSENT),
            observe("power", 10),
            observe("power", 14, status=ObservationStatus.UNDONE),
            observe("resistor", 18),
            observe("power", 22),
            observe("lit", 26),
        ],
    )
    assert result.verdict is Verdict.VERIFIED
    violation = next(a for a in result.alerts if a.kind is AlertKind.WRONG_ORDER)
    assert violation.resolved is True
    assert violation.resolved_at == 22
    assert result.step_states["power"] is StepState.DONE


def test_redo_without_correction_does_not_resolve(graph):
    """Seeing the resistor later does not undo an earlier powered mistake."""
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("ground", 6),
            observe("resistor", 9, status=ObservationStatus.ABSENT),
            observe("power", 10),
            observe("resistor", 14),
            observe("power", 18),
        ],
    )
    assert result.verdict is Verdict.NOT_VERIFIED
    violation = next(a for a in result.alerts if a.kind is AlertKind.WRONG_ORDER)
    assert violation.resolved is False
    assert any(
        "has not been corrected" in event.message for event in result.events
    )


def test_duplicate_and_overlapping_observations_are_idempotent(graph):
    """One event described by two overlapping windows is one confirmation."""
    base = [
        observe("led", 2),
        observe("resistor", 6),
        observe("ground", 10),
        observe("power", 14),
        observe("lit", 18),
    ]
    duplicated = base + [
        observe("ground", 10.2, window="w_overlap"),
        observe("power", 14.1, window="w_overlap"),
    ]
    once = assess_attempt(graph, base)
    twice = assess_attempt(graph, duplicated)
    assert twice.verdict == once.verdict
    assert twice.step_states == once.step_states
    assert any(e.type.value == "duplicate_ignored" for e in twice.events)


def test_live_mode_needs_independent_confirmation(graph):
    """In live mode one sighting is not enough, and an overlap is not two."""
    config = EngineConfig(mode="live", live_confirmations_required=2, independent_gap_s=1.0)
    single = assess_attempt(graph, [observe("led", 2)], config)
    assert single.step_states["led"] is not StepState.DONE
    assert any(e.type.value == "confirmation_pending" for e in single.events)

    overlapping = assess_attempt(
        graph, [observe("led", 2), observe("led", 2.3, window="w_overlap")], config
    )
    assert overlapping.step_states["led"] is not StepState.DONE
    assert any(e.type.value == "duplicate_ignored" for e in overlapping.events)

    independent = assess_attempt(
        graph, [observe("led", 2), observe("led", 5, window="w2")], config
    )
    assert independent.step_states["led"] is StepState.DONE


def test_undone_step_reverts_and_unsettles_dependents(graph):
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("resistor", 6),
            observe("ground", 10),
            observe("power", 14),
            observe("lit", 18),
            observe("power", 22, status=ObservationStatus.UNDONE),
        ],
    )
    assert any(e.type.value == "step_reverted" for e in result.events)
    # The attempt ends with power no longer established, so neither it nor the
    # step that rested on it may be reported as done.
    assert result.step_states["power"] is not StepState.DONE
    assert result.step_states["lit"] is not StepState.DONE
    assert result.verdict is Verdict.INCONCLUSIVE


def test_undone_for_a_step_that_was_never_done_is_ignored(graph):
    result = assess_attempt(graph, [observe("led", 2, status=ObservationStatus.UNDONE)])
    assert result.step_states["led"] is not StepState.DONE
    ignored = [e for e in result.events if e.type.value == "duplicate_ignored"]
    assert ignored and "never established as done" in ignored[0].message


def test_missing_required_step_at_the_end_is_inconclusive(graph):
    result = assess_attempt(graph, [observe("led", 2), observe("resistor", 6)])
    assert result.verdict is Verdict.INCONCLUSIVE
    missing = [a for a in result.alerts if a.kind is AlertKind.MISSING_REQUIRED]
    assert missing
    assert all(not alert.supported for alert in missing)


def test_absent_required_step_at_the_end_is_a_supported_failure(graph):
    result = assess_attempt(
        graph,
        [
            observe("led", 2),
            observe("ground", 6),
            observe("resistor", 8, status=ObservationStatus.ABSENT),
        ],
    )
    assert result.verdict is Verdict.NOT_VERIFIED
    assert result.step_states["resistor"] is StepState.SKIPPED


def test_optional_step_does_not_block_a_pass(graph):
    optional = graph.model_copy(
        update={
            "steps": [
                step.model_copy(update={"required": False})
                if step.step_id == "lit"
                else step
                for step in graph.steps
            ]
        }
    )
    result = assess_attempt(
        optional,
        [
            observe("led", 2),
            observe("resistor", 6),
            observe("ground", 10),
            observe("power", 14),
        ],
    )
    assert result.verdict is Verdict.VERIFIED


def test_observation_for_an_unknown_step_is_ignored(graph):
    result = assess_attempt(graph, [observe("not_a_step", 2)])
    assert any(e.type.value == "duplicate_ignored" for e in result.events)
    assert "not_a_step" not in result.step_states


def test_in_progress_marks_a_step_started(graph):
    result = assess_attempt(
        graph, [observe("led", 2, status=ObservationStatus.IN_PROGRESS)]
    )
    started = [e for e in result.events if e.type.value == "step_started"]
    assert started and started[0].step_id == "led"
    # Started is not finished: the attempt ends without a confirmed checkpoint.
    assert result.step_states["led"] is StepState.UNCERTAIN
    assert result.verdict is Verdict.INCONCLUSIVE


def test_cycle_is_rejected_by_validation():
    cyclic = SkillGraph(
        skill_id="s",
        title="Cyclic",
        steps=[
            Step(step_id="a", title="A", checkpoint="a", depends_on=["b"]),
            Step(step_id="b", title="B", checkpoint="b", depends_on=["a"]),
        ],
    )
    result = validate_procedure(cyclic)
    assert not result.ok
    codes = {issue.code for issue in result.issues}
    assert "cycle" in codes
    message = next(i.message for i in result.issues if i.code == "cycle")
    assert "A" in message and "B" in message


def test_rule_that_closes_a_cycle_is_rejected(graph):
    looped = graph.model_copy(
        update={
            "rules": [
                *graph.rules,
                OrderingRule(
                    rule_id="r2",
                    before="power",
                    after="resistor",
                    reason="contradicts r1",
                ),
            ]
        }
    )
    assert not validate_procedure(looped).ok


def test_replay_is_byte_identical(graph):
    observations = [
        observe("led", 2),
        observe("ground", 6),
        observe("resistor", 9, status=ObservationStatus.ABSENT),
        observe("power", 10),
        observe("lit", 14),
    ]
    first = assess_attempt(graph, observations)
    second = assess_attempt(graph, list(reversed(observations)))
    assert first.model_dump_json() == second.model_dump_json()


def test_random_valid_orders_all_verify(graph):
    """Any topological order of the reviewed graph must pass."""
    rng = random.Random(20260927)
    for _ in range(25):
        times = {"led": 2.0}
        remaining = ["resistor", "ground", "power", "lit"]
        placed = ["led"]
        clock = 6.0
        while remaining:
            ready = [
                step_id
                for step_id in remaining
                if all(
                    dependency in placed
                    for dependency in _predecessors(graph, step_id)
                )
            ]
            chosen = rng.choice(ready)
            times[chosen] = clock
            clock += 4.0
            placed.append(chosen)
            remaining.remove(chosen)
        observations = [observe(step_id, t) for step_id, t in times.items()]
        rng.shuffle(observations)
        result = assess_attempt(graph, observations)
        assert result.verdict is Verdict.VERIFIED, times


def _predecessors(graph: SkillGraph, step_id: str) -> list[str]:
    step = next(s for s in graph.steps if s.step_id == step_id)
    predecessors = list(step.depends_on)
    predecessors += [r.before for r in graph.rules if r.after == step_id]
    return predecessors
