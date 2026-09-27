"""The deterministic assessment engine.

Pure Python: no network, disk, clock, or randomness. Its inputs are a reviewed
skill graph, an ordered observation log, and explicit configuration; its outputs
are an ordered event log, step states, alerts, and a verdict. Running it twice
over the same inputs must produce byte-identical output, which is what
`/api/attempts/{id}/replay` checks.

The engine never upgrades an uncertain observation into a certainty. Two
distinctions carry most of the design:

* missing evidence versus explicit absence. Only an `absent` observation, made
  while the checkpoint area was visible, can support a claim that a learner
  skipped a step.
* proposing versus deciding. The model supplies observations; every state
  transition below is decided here, from the reviewed procedure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import (
    Alert,
    AlertKind,
    EngineConfig,
    EngineEvent,
    EngineEventType,
    EngineResult,
    EvidenceRef,
    Observation,
    ObservationStatus,
    SkillGraph,
    Step,
    StepState,
    Verdict,
)

# Step states that mean "the checkpoint was positively established".
_ESTABLISHED = (StepState.DONE,)


def observation_sort_key(observation: Observation) -> tuple[float, float, str, str]:
    """Source-time order with a documented, total tie-break.

    Two observations with the same time range are ordered by step id and then
    observation id, so a provider returning windows out of order cannot change
    the verdict.
    """
    return (
        observation.t_start,
        observation.t_end,
        observation.step_id,
        observation.observation_id,
    )


@dataclass
class _StepRuntime:
    step: Step
    state: StepState = StepState.PENDING
    confirmations: list[float] = field(default_factory=list)
    done_at: float | None = None
    absent_at: list[float] = field(default_factory=list)
    absent_evidence: EvidenceRef | None = None
    uncertain_seen: bool = False
    ignored_low_confidence: int = 0
    last_completed_window_start: float | None = None
    undone_at: float | None = None


@dataclass
class _OpenViolation:
    """State machine for correcting one wrong-order violation.

    A violation is corrected only by the full sequence: the violating action is
    undone, the missing prerequisite is then completed, and the violating action
    is performed again afterwards.
    """

    alert: Alert
    violating_step: str
    prerequisite: str
    undone_at: float | None = None
    prereq_done_at: float | None = None


class _Engine:
    def __init__(
        self, graph: SkillGraph, config: EngineConfig
    ) -> None:  # pragma: no cover - trivial
        self.graph = graph
        self.config = config
        self.steps: dict[str, _StepRuntime] = {
            step.step_id: _StepRuntime(step=step) for step in graph.steps
        }
        self.events: list[EngineEvent] = []
        self.alerts: list[Alert] = []
        self.open_violations: list[_OpenViolation] = []
        self._seq = 0
        self._alert_seq = 0
        # predecessors[step] -> ordered list of (predecessor_id, rule_id or None)
        self.predecessors: dict[str, list[tuple[str, str | None]]] = {
            step.step_id: [] for step in graph.steps
        }
        for step in graph.steps:
            for dep in step.depends_on:
                if dep in self.steps:
                    self._add_predecessor(step.step_id, dep, None)
        for rule in graph.rules:
            if rule.before in self.steps and rule.after in self.steps:
                self._add_predecessor(rule.after, rule.before, rule.rule_id)
        self.dependents: dict[str, list[str]] = {
            step.step_id: [] for step in graph.steps
        }
        for step_id, preds in self.predecessors.items():
            for pred_id, _rule in preds:
                if step_id not in self.dependents[pred_id]:
                    self.dependents[pred_id].append(step_id)

    # -- helpers -----------------------------------------------------------

    def _add_predecessor(self, step_id: str, pred_id: str, rule_id: str | None) -> None:
        existing = self.predecessors[step_id]
        for index, (known, known_rule) in enumerate(existing):
            if known == pred_id:
                if known_rule is None and rule_id is not None:
                    existing[index] = (known, rule_id)
                return
        existing.append((pred_id, rule_id))

    def _emit(
        self,
        event_type: EngineEventType,
        *,
        t: float,
        message: str,
        step_id: str | None = None,
        rule_id: str | None = None,
        alert_id: str | None = None,
        observation: Observation | None = None,
        evidence: EvidenceRef | None = None,
    ) -> EngineEvent:
        self._seq += 1
        event = EngineEvent(
            seq=self._seq,
            type=event_type,
            step_id=step_id,
            rule_id=rule_id,
            alert_id=alert_id,
            t=t,
            message=message,
            observation_id=observation.observation_id if observation else None,
            evidence=evidence
            or (observation.evidence if observation is not None else None),
        )
        self.events.append(event)
        return event

    def _new_alert_id(self, kind: AlertKind) -> str:
        self._alert_seq += 1
        return f"alert_{self._alert_seq}_{kind.value}"

    def _title(self, step_id: str) -> str:
        runtime = self.steps.get(step_id)
        return runtime.step.title if runtime else step_id

    def _is_independent(self, runtime: _StepRuntime, t_start: float) -> bool:
        """Overlapping windows describing one event confirm it only once."""
        if not runtime.confirmations:
            return True
        return (t_start - runtime.confirmations[-1]) >= self.config.independent_gap_s

    # -- observation handling ---------------------------------------------

    def run(self, observations: list[Observation]) -> EngineResult:
        ordered = sorted(observations, key=observation_sort_key)
        for observation in ordered:
            self._handle(observation)
        return self._finalize(ordered)

    def _handle(self, observation: Observation) -> None:
        runtime = self.steps.get(observation.step_id)
        if runtime is None:
            self._emit(
                EngineEventType.DUPLICATE_IGNORED,
                t=observation.t_start,
                step_id=observation.step_id,
                observation=observation,
                message=(
                    f"Ignored an observation for {observation.step_id}, which is not "
                    "a step in this procedure."
                ),
            )
            return

        if observation.status is ObservationStatus.UNCERTAIN:
            runtime.uncertain_seen = True
            self._emit(
                EngineEventType.UNCERTAIN_OBSERVATION,
                t=observation.t_start,
                step_id=runtime.step.step_id,
                observation=observation,
                message=(
                    f"Could not tell whether {runtime.step.title} happened: "
                    f"{observation.rationale or 'no clear view'}."
                ),
            )
            if runtime.state is StepState.PENDING:
                runtime.state = StepState.UNCERTAIN
            return

        if observation.confidence < self.config.min_confidence:
            runtime.ignored_low_confidence += 1
            runtime.uncertain_seen = True
            self._emit(
                EngineEventType.LOW_CONFIDENCE_IGNORED,
                t=observation.t_start,
                step_id=runtime.step.step_id,
                observation=observation,
                message=(
                    f"Ignored a low-confidence {observation.status.value} observation "
                    f"of {runtime.step.title} "
                    f"({observation.confidence:.2f} < {self.config.min_confidence:.2f}); "
                    "it cannot establish completion, absence, or an undo."
                ),
            )
            if runtime.state is StepState.PENDING:
                runtime.state = StepState.UNCERTAIN
            return

        if observation.status is ObservationStatus.IN_PROGRESS:
            self._handle_in_progress(runtime, observation)
        elif observation.status is ObservationStatus.COMPLETED:
            self._handle_completed(runtime, observation)
        elif observation.status is ObservationStatus.UNDONE:
            self._handle_undone(runtime, observation)
        elif observation.status is ObservationStatus.ABSENT:
            self._handle_absent(runtime, observation)

    def _handle_in_progress(
        self, runtime: _StepRuntime, observation: Observation
    ) -> None:
        if runtime.state in (StepState.PENDING, StepState.UNCERTAIN):
            runtime.state = StepState.IN_PROGRESS
            self._emit(
                EngineEventType.STEP_STARTED,
                t=observation.t_start,
                step_id=runtime.step.step_id,
                observation=observation,
                message=f"{runtime.step.title} started.",
            )

    def _handle_completed(
        self, runtime: _StepRuntime, observation: Observation
    ) -> None:
        step_id = runtime.step.step_id

        if runtime.state is StepState.DONE:
            self._emit(
                EngineEventType.DUPLICATE_IGNORED,
                t=observation.t_start,
                step_id=step_id,
                observation=observation,
                message=(
                    f"{runtime.step.title} was already established as done; "
                    "the repeated observation changes nothing."
                ),
            )
            return

        if not self._is_independent(runtime, observation.t_start):
            self._emit(
                EngineEventType.DUPLICATE_IGNORED,
                t=observation.t_start,
                step_id=step_id,
                observation=observation,
                message=(
                    f"Another window already reported this completion of "
                    f"{runtime.step.title} within "
                    f"{self.config.independent_gap_s:g}s, so it is the same event, "
                    "not an independent confirmation."
                ),
            )
            return

        runtime.confirmations.append(observation.t_start)
        needed = self.config.required_confirmations()
        if len(runtime.confirmations) < needed:
            if runtime.state in (StepState.PENDING, StepState.UNCERTAIN):
                runtime.state = StepState.IN_PROGRESS
            self._emit(
                EngineEventType.CONFIRMATION_PENDING,
                t=observation.t_start,
                step_id=step_id,
                observation=observation,
                message=(
                    f"{runtime.step.title} reported complete "
                    f"({len(runtime.confirmations)} of {needed} independent "
                    "confirmations needed in this mode)."
                ),
            )
            return

        correction = self._try_resolve_violation(runtime, observation)
        blocking = [] if correction else self._check_predecessors(runtime, observation)
        if blocking:
            return

        runtime.state = StepState.DONE
        runtime.done_at = observation.t_start
        runtime.last_completed_window_start = observation.t_start
        self._emit(
            EngineEventType.STEP_DONE,
            t=observation.t_start,
            step_id=step_id,
            observation=observation,
            message=f"{runtime.step.title} confirmed done.",
        )
        self._note_prereq_progress(step_id, observation.t_start)

    def _check_predecessors(
        self, runtime: _StepRuntime, observation: Observation
    ) -> list[str]:
        """Return the predecessor ids that block this completion, if any."""
        blocking: list[str] = []
        step_id = runtime.step.step_id
        for pred_id, rule_id in self.predecessors[step_id]:
            pred = self.steps[pred_id]
            if pred.state in _ESTABLISHED and (
                pred.done_at is not None and pred.done_at <= observation.t_start
            ):
                continue

            absent_before = [t for t in pred.absent_at if t <= observation.t_start]
            if absent_before:
                # Supported wrong order: the prerequisite's result was visibly
                # absent when this step was performed.
                alert_id = self._new_alert_id(AlertKind.WRONG_ORDER)
                reason = self._rule_reason(rule_id)
                alert = Alert(
                    alert_id=alert_id,
                    kind=AlertKind.WRONG_ORDER,
                    step_id=step_id,
                    rule_id=rule_id,
                    message=(
                        f"{runtime.step.title} was performed while "
                        f"{self._title(pred_id)} was visibly not done."
                        + (f" {reason}" if reason else "")
                    ),
                    opened_at=observation.t_start,
                    opened_evidence=observation.evidence,
                    supported=True,
                )
                self.alerts.append(alert)
                self.open_violations.append(
                    _OpenViolation(
                        alert=alert,
                        violating_step=step_id,
                        prerequisite=pred_id,
                    )
                )
                if pred.state is not StepState.DONE:
                    pred.state = StepState.SKIPPED
                runtime.state = StepState.VIOLATION
                self._emit(
                    EngineEventType.ORDER_VIOLATION,
                    t=observation.t_start,
                    step_id=step_id,
                    rule_id=rule_id,
                    alert_id=alert_id,
                    observation=observation,
                    message=alert.message,
                )
                blocking.append(pred_id)
                continue

            # Missing evidence, not absence: this cannot prove a skip.
            alert_id = self._new_alert_id(AlertKind.PREREQ_UNCONFIRMED)
            alert = Alert(
                alert_id=alert_id,
                kind=AlertKind.PREREQ_UNCONFIRMED,
                step_id=pred_id,
                rule_id=rule_id,
                message=(
                    f"{runtime.step.title} was observed complete, but "
                    f"{self._title(pred_id)} was never confirmed and was not "
                    "observed absent. The evidence cannot establish whether it "
                    "was done."
                ),
                opened_at=observation.t_start,
                opened_evidence=observation.evidence,
                supported=False,
            )
            self.alerts.append(alert)
            if pred.state in (StepState.PENDING, StepState.IN_PROGRESS):
                pred.state = StepState.UNCERTAIN
            pred.uncertain_seen = True
            self._emit(
                EngineEventType.PREREQ_UNCONFIRMED,
                t=observation.t_start,
                step_id=pred_id,
                rule_id=rule_id,
                alert_id=alert_id,
                observation=observation,
                message=alert.message,
            )
        return blocking

    def _rule_reason(self, rule_id: str | None) -> str:
        if rule_id is None:
            return ""
        for rule in self.graph.rules:
            if rule.rule_id == rule_id:
                return rule.reason
        return ""

    def _try_resolve_violation(
        self, runtime: _StepRuntime, observation: Observation
    ) -> bool:
        """Resolve a wrong-order alert only after a full correction sequence."""
        step_id = runtime.step.step_id
        for violation in self.open_violations:
            if violation.violating_step != step_id or violation.alert.resolved:
                continue
            if violation.undone_at is None or violation.prereq_done_at is None:
                self._emit(
                    EngineEventType.ORDER_VIOLATION,
                    t=observation.t_start,
                    step_id=step_id,
                    rule_id=violation.alert.rule_id,
                    alert_id=violation.alert.alert_id,
                    observation=observation,
                    message=(
                        f"{runtime.step.title} was repeated, but the earlier "
                        "wrong-order action has not been corrected: "
                        + self._missing_correction_text(violation)
                    ),
                )
                return False
            if observation.t_start < violation.prereq_done_at:
                return False
            violation.alert.resolved = True
            violation.alert.resolved_at = observation.t_start
            violation.alert.resolved_evidence = observation.evidence
            self._emit(
                EngineEventType.ALERT_RESOLVED,
                t=observation.t_start,
                step_id=step_id,
                rule_id=violation.alert.rule_id,
                alert_id=violation.alert.alert_id,
                observation=observation,
                message=(
                    f"Wrong order corrected: {runtime.step.title} was undone, "
                    f"{self._title(violation.prerequisite)} was completed, and "
                    f"{runtime.step.title} was performed again afterwards."
                ),
            )
            return True
        return False

    def _missing_correction_text(self, violation: _OpenViolation) -> str:
        if violation.undone_at is None:
            return (
                f"{self._title(violation.violating_step)} was never observed undone."
            )
        return (
            f"{self._title(violation.prerequisite)} was not confirmed after "
            f"{self._title(violation.violating_step)} was undone."
        )

    def _handle_undone(self, runtime: _StepRuntime, observation: Observation) -> None:
        step_id = runtime.step.step_id
        if runtime.state not in (
            StepState.DONE,
            StepState.VIOLATION,
            StepState.IN_PROGRESS,
        ):
            self._emit(
                EngineEventType.DUPLICATE_IGNORED,
                t=observation.t_start,
                step_id=step_id,
                observation=observation,
                message=(
                    f"{runtime.step.title} was reported undone although it was "
                    f"never established as done (state: {runtime.state.value})."
                ),
            )
            return

        previous = runtime.state
        runtime.state = StepState.PENDING
        runtime.confirmations = []
        runtime.done_at = None
        runtime.undone_at = observation.t_start
        self._emit(
            EngineEventType.STEP_REVERTED,
            t=observation.t_start,
            step_id=step_id,
            observation=observation,
            message=(
                f"{runtime.step.title} was undone "
                f"(was {previous.value}); it is no longer established."
            ),
        )

        for violation in self.open_violations:
            if violation.violating_step == step_id and not violation.alert.resolved:
                violation.undone_at = observation.t_start
                violation.prereq_done_at = None

        # A dependent that rested on this step is no longer supported.
        for dependent_id in self.dependents.get(step_id, []):
            dependent = self.steps[dependent_id]
            if dependent.state is StepState.DONE:
                dependent.state = StepState.UNCERTAIN
                dependent.uncertain_seen = True
                alert_id = self._new_alert_id(AlertKind.PREREQ_UNCONFIRMED)
                self.alerts.append(
                    Alert(
                        alert_id=alert_id,
                        kind=AlertKind.PREREQ_UNCONFIRMED,
                        step_id=dependent_id,
                        message=(
                            f"{dependent.step.title} was established earlier, but "
                            f"{runtime.step.title} was later undone, so its result "
                            "can no longer be assumed to hold."
                        ),
                        opened_at=observation.t_start,
                        opened_evidence=observation.evidence,
                        supported=False,
                    )
                )
                self._emit(
                    EngineEventType.PREREQ_UNCONFIRMED,
                    t=observation.t_start,
                    step_id=dependent_id,
                    alert_id=alert_id,
                    observation=observation,
                    message=self.alerts[-1].message,
                )

    def _handle_absent(self, runtime: _StepRuntime, observation: Observation) -> None:
        step_id = runtime.step.step_id
        runtime.absent_at.append(observation.t_start)
        runtime.absent_evidence = observation.evidence
        self._emit(
            EngineEventType.ABSENCE_RECORDED,
            t=observation.t_start,
            step_id=step_id,
            observation=observation,
            message=(
                f"The checkpoint for {runtime.step.title} was visible and its "
                f"expected result was not there: "
                f"{observation.rationale or runtime.step.checkpoint or 'not present'}."
            ),
        )
        if runtime.state is StepState.DONE:
            # Conflicting evidence: keep the established state but stop treating
            # it as certain.
            runtime.uncertain_seen = True

    def _note_prereq_progress(self, step_id: str, t: float) -> None:
        """Record that a prerequisite was completed during a correction."""
        for violation in self.open_violations:
            if (
                violation.prerequisite == step_id
                and not violation.alert.resolved
                and violation.undone_at is not None
                and t >= violation.undone_at
            ):
                violation.prereq_done_at = t

    # -- verdict -----------------------------------------------------------

    def _finalize(self, ordered: list[Observation]) -> EngineResult:
        last_t = ordered[-1].t_end if ordered else 0.0
        reasons: list[str] = []

        for step_id, runtime in self.steps.items():
            if not runtime.step.required:
                continue
            if runtime.state is StepState.DONE:
                continue
            if runtime.state is StepState.VIOLATION:
                continue
            if runtime.absent_at and runtime.state is not StepState.DONE:
                runtime.state = StepState.SKIPPED
                alert_id = self._new_alert_id(AlertKind.MISSING_REQUIRED)
                self.alerts.append(
                    Alert(
                        alert_id=alert_id,
                        kind=AlertKind.MISSING_REQUIRED,
                        step_id=step_id,
                        message=(
                            f"{runtime.step.title} is required and its expected "
                            "result was visibly absent, and it was never confirmed."
                        ),
                        opened_at=runtime.absent_at[0],
                        opened_evidence=runtime.absent_evidence,
                        supported=True,
                    )
                )
                self._emit(
                    EngineEventType.STEP_SKIPPED,
                    t=runtime.absent_at[0],
                    step_id=step_id,
                    alert_id=alert_id,
                    evidence=runtime.absent_evidence,
                    message=self.alerts[-1].message,
                )
                continue

            alert_id = self._new_alert_id(AlertKind.MISSING_REQUIRED)
            self.alerts.append(
                Alert(
                    alert_id=alert_id,
                    kind=AlertKind.MISSING_REQUIRED,
                    step_id=step_id,
                    message=(
                        f"{runtime.step.title} is required and was never confirmed. "
                        "It was also never observed absent, so this footage cannot "
                        "show whether it happened."
                    ),
                    opened_at=last_t,
                    supported=False,
                )
            )
            runtime.state = StepState.UNCERTAIN
            self._emit(
                EngineEventType.MISSING_REQUIRED,
                t=last_t,
                step_id=step_id,
                alert_id=alert_id,
                message=self.alerts[-1].message,
            )

        unresolved = [a for a in self.alerts if not a.resolved]
        supported_failures = [a for a in unresolved if a.supported]
        unsupported = [a for a in unresolved if not a.supported]
        required_done = [
            runtime
            for runtime in self.steps.values()
            if runtime.step.required and runtime.state is StepState.DONE
        ]
        required_total = [r for r in self.steps.values() if r.step.required]

        if supported_failures:
            verdict = Verdict.NOT_VERIFIED
            reasons.extend(alert.message for alert in supported_failures)
        elif len(required_done) == len(required_total) and not unsupported:
            verdict = Verdict.VERIFIED
            reasons.append(
                "Every required checkpoint was independently confirmed and no "
                "ordering rule was violated."
            )
            resolved = [a for a in self.alerts if a.resolved]
            if resolved:
                reasons.append(
                    f"{len(resolved)} earlier problem"
                    f"{'s' if len(resolved) != 1 else ''} was corrected during the "
                    "attempt."
                )
        else:
            verdict = Verdict.INCONCLUSIVE
            reasons.extend(alert.message for alert in unsupported)
            if not unsupported:
                reasons.append(
                    "The available evidence does not establish completion or a "
                    "specific failure."
                )

        self._emit(
            EngineEventType.VERDICT,
            t=last_t,
            message=f"Verdict: {verdict.value}.",
        )

        return EngineResult(
            step_states={
                step.step_id: self.steps[step.step_id].state for step in self.graph.steps
            },
            events=self.events,
            alerts=self.alerts,
            verdict=verdict,
            reasons=reasons,
        )


def assess_attempt(
    graph: SkillGraph,
    observations: list[Observation],
    config: EngineConfig | None = None,
) -> EngineResult:
    """Assess an observation log against a reviewed procedure."""
    return _Engine(graph, config or EngineConfig()).run(list(observations))


def replay(
    graph: SkillGraph,
    observations: list[Observation],
    config: EngineConfig | None = None,
) -> EngineResult:
    """Alias that documents intent at call sites: same inputs, same output."""
    return assess_attempt(graph, observations, config)
