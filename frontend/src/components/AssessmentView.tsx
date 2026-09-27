/**
 * The assessment surface shared by Practice and Verdict: a step checklist, the
 * alert feed, and the engine's event log. Everything here is clickable evidence
 * — a click seeks the source video to the moment the claim rests on.
 */
import { AlertTriangle, CheckCircle2, CircleHelp, Clock } from "lucide-react";
import type {
  Alert,
  EngineEvent,
  EvidenceRef,
  Observation,
  SkillGraph,
  StepState,
} from "@/types/api";
import { formatTime, percent } from "@/lib/format";
import { StepStateBadge } from "@/components/Badges";
import { EmptyState } from "@/components/Panels";

export function StepChecklist({
  skill,
  states,
  observations,
  onEvidence,
}: {
  skill: SkillGraph;
  states: Record<string, StepState>;
  observations: Observation[];
  onEvidence: (evidence: EvidenceRef) => void;
}) {
  return (
    <ol className="flex flex-col gap-2" data-testid="step-checklist">
      {(skill.steps ?? []).map((step, index) => {
        const state = states[step.step_id] ?? "pending";
        const forStep = observations.filter(
          (observation) => observation.step_id === step.step_id,
        );
        return (
          <li
            key={step.step_id}
            className="rounded-lg border border-line bg-surface-raised p-3"
            data-testid={`checklist-item-${step.step_id}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono text-xs text-ink-faint">{index + 1}</span>
              <span className="min-w-0 flex-1 text-sm font-medium text-ink">
                {step.title}
              </span>
              <StepStateBadge state={state} />
            </div>
            {step.checkpoint && (
              <p className="mt-1 text-xs text-ink-muted">Checkpoint: {step.checkpoint}</p>
            )}
            {forStep.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1">
                {forStep.map((observation) => (
                  <li key={observation.observation_id}>
                    <button
                      type="button"
                      className="flex w-full items-start gap-2 rounded px-1.5 py-1 text-left text-xs text-ink-muted hover:bg-surface-sunken"
                      onClick={() => onEvidence(observation.evidence)}
                      data-testid="evidence-link"
                    >
                      <Clock size={12} className="mt-0.5 shrink-0" />
                      <span className="mono shrink-0">
                        {formatTime(observation.t_start)}
                      </span>
                      <span className="min-w-0 flex-1">
                        {observation.status} · {percent(observation.confidence)} ·{" "}
                        {observation.rationale}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function AlertFeed({
  alerts,
  onEvidence,
}: {
  alerts: Alert[];
  onEvidence: (evidence: EvidenceRef) => void;
}) {
  if (alerts.length === 0) {
    return (
      <EmptyState
        title="No alerts"
        detail="The engine found nothing that contradicts the reviewed procedure."
      />
    );
  }
  return (
    <ul className="flex flex-col gap-2" data-testid="alert-feed">
      {alerts.map((alert) => {
        const color = alert.resolved
          ? "var(--ok)"
          : alert.supported
            ? "var(--danger)"
            : "var(--unsure)";
        const Icon = alert.resolved
          ? CheckCircle2
          : alert.supported
            ? AlertTriangle
            : CircleHelp;
        return (
          <li
            key={alert.alert_id}
            className="rounded-lg border p-3"
            style={{ borderColor: color }}
            data-testid={`alert-${alert.kind}`}
          >
            <div className="flex items-start gap-2">
              <Icon size={16} style={{ color }} className="mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink">{alert.message}</p>
                <p className="mt-1 text-xs" style={{ color }}>
                  {alert.resolved
                    ? "Corrected later in the attempt"
                    : alert.supported
                      ? "Supported by visible evidence"
                      : "Not supported by absence evidence — this cannot prove a failure"}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {alert.opened_evidence && (
                    <button
                      type="button"
                      className="btn btn-ghost mono px-2 py-1 text-xs"
                      onClick={() => onEvidence(alert.opened_evidence!)}
                      data-testid="alert-evidence"
                    >
                      opened {formatTime(alert.opened_at)}
                    </button>
                  )}
                  {alert.resolved && alert.resolved_evidence && (
                    <button
                      type="button"
                      className="btn btn-ghost mono px-2 py-1 text-xs"
                      onClick={() => onEvidence(alert.resolved_evidence!)}
                    >
                      resolved {formatTime(alert.resolved_at ?? 0)}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function EventLog({
  events,
  onEvidence,
}: {
  events: EngineEvent[];
  onEvidence: (evidence: EvidenceRef) => void;
}) {
  if (events.length === 0) {
    return <p className="text-sm text-ink-muted">No engine events yet.</p>;
  }
  return (
    <ol className="flex flex-col gap-1" data-testid="event-log">
      {events.map((event) => (
        <li key={event.seq}>
          <button
            type="button"
            className="flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-surface-sunken disabled:hover:bg-transparent"
            onClick={() => event.evidence && onEvidence(event.evidence)}
            disabled={!event.evidence}
          >
            <span className="mono shrink-0 text-ink-faint">{formatTime(event.t)}</span>
            <span className="mono shrink-0 text-ink-faint">{event.type}</span>
            <span className="min-w-0 flex-1 text-ink-muted">{event.message}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}
