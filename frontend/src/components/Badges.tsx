/**
 * State badges. Each one carries an icon and a word as well as a colour, so the
 * meaning survives colour blindness, a projector, and a grayscale screenshot.
 */
import {
  AlertTriangle,
  Ban,
  Check,
  CircleDashed,
  CircleHelp,
  FlaskConical,
  Loader,
  Radio,
  Database,
} from "lucide-react";
import type { ComponentType } from "react";
import type { Provenance, StepState, Verdict } from "@/types/api";
import {
  PROVENANCE_MEANING,
  STEP_STATE_COLOR,
  STEP_STATE_LABEL,
  VERDICT_COLOR,
  VERDICT_LABEL,
  VERDICT_MEANING,
} from "@/lib/format";

const STEP_ICON: Record<StepState, ComponentType<{ size?: number }>> = {
  pending: CircleDashed,
  in_progress: Loader,
  done: Check,
  skipped: Ban,
  violation: AlertTriangle,
  uncertain: CircleHelp,
};

export function StepStateBadge({ state }: { state: StepState }) {
  const Icon = STEP_ICON[state];
  const color = STEP_STATE_COLOR[state];
  return (
    <span
      className="chip"
      style={{ color, borderColor: color, background: "transparent" }}
      data-testid={`step-state-${state}`}
    >
      <Icon size={13} />
      {STEP_STATE_LABEL[state]}
    </span>
  );
}

export function VerdictBadge({
  verdict,
  large = false,
}: {
  verdict: Verdict;
  large?: boolean;
}) {
  const color = VERDICT_COLOR[verdict];
  const Icon =
    verdict === "VERIFIED"
      ? Check
      : verdict === "NOT_VERIFIED"
        ? AlertTriangle
        : CircleHelp;
  return (
    <span
      className={`chip ${large ? "px-3 py-1.5 text-sm" : ""}`}
      style={{ color, borderColor: color, background: "transparent" }}
      title={VERDICT_MEANING[verdict]}
      data-testid={`verdict-${verdict}`}
    >
      <Icon size={large ? 18 : 13} />
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

export function ProvenanceBadge({
  provenance,
  compact = false,
}: {
  provenance: Provenance;
  compact?: boolean;
}) {
  const Icon =
    provenance === "LIVE" ? Radio : provenance === "CACHED" ? Database : FlaskConical;
  const color =
    provenance === "LIVE"
      ? "var(--ok)"
      : provenance === "CACHED"
        ? "var(--accent)"
        : "var(--warn)";
  return (
    <span
      className="chip mono"
      style={{ color, borderColor: color, background: "transparent" }}
      title={PROVENANCE_MEANING[provenance]}
      data-testid="provenance-badge"
    >
      <Icon size={13} />
      {provenance}
      {!compact && provenance === "MOCK" && (
        <span className="font-sans font-normal text-ink-muted">· not a model result</span>
      )}
    </span>
  );
}

export function ProposedBadge({ confirmed }: { confirmed: boolean }) {
  return confirmed ? (
    <span
      className="chip"
      style={{ color: "var(--ok)", borderColor: "var(--ok)" }}
      data-testid="rule-confirmed"
    >
      <Check size={13} /> Confirmed by expert
    </span>
  ) : (
    <span
      className="chip"
      style={{ color: "var(--warn)", borderColor: "var(--warn)" }}
      data-testid="rule-proposed"
    >
      <CircleHelp size={13} /> Proposed by model
    </span>
  );
}
