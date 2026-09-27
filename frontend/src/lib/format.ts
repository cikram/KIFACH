/** Small pure helpers shared by the screens, unit tested in format.test.ts. */
import type { Provenance, StepState, Verdict } from "@/types/api";

export function formatTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "--:--";
  const clamped = Math.max(0, seconds);
  const minutes = Math.floor(clamped / 60);
  const rest = clamped - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${rest.toFixed(1).padStart(4, "0")}`;
}

export function formatRange(start: number, end: number): string {
  return `${formatTime(start)} – ${formatTime(end)}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const STEP_STATE_LABEL: Record<StepState, string> = {
  pending: "Not started",
  in_progress: "In progress",
  done: "Done",
  skipped: "Skipped",
  violation: "Wrong order",
  uncertain: "Uncertain",
};

/** Colour is paired with these labels everywhere; never used on its own. */
export const STEP_STATE_COLOR: Record<StepState, string> = {
  pending: "var(--pending)",
  in_progress: "var(--accent)",
  done: "var(--ok)",
  skipped: "var(--warn)",
  violation: "var(--danger)",
  uncertain: "var(--unsure)",
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  VERIFIED: "Verified",
  NOT_VERIFIED: "Not verified",
  INCONCLUSIVE: "Inconclusive",
};

export const VERDICT_COLOR: Record<Verdict, string> = {
  VERIFIED: "var(--ok)",
  NOT_VERIFIED: "var(--danger)",
  INCONCLUSIVE: "var(--unsure)",
};

export const VERDICT_MEANING: Record<Verdict, string> = {
  VERIFIED: "Every required checkpoint was confirmed and no rule was broken.",
  NOT_VERIFIED: "The evidence supports a specific failure.",
  INCONCLUSIVE: "The evidence cannot establish completion or a specific failure.",
};

export const PROVENANCE_MEANING: Record<Provenance, string> = {
  LIVE: "Produced by a live model call during this run.",
  CACHED: "A genuine model response replayed from the on-disk cache.",
  MOCK: "Scripted offline output. Not a model result.",
};

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function pluralize(count: number, single: string, plural?: string): string {
  return `${count} ${count === 1 ? single : (plural ?? `${single}s`)}`;
}

/** A stable, readable id fragment for the mono badges in the UI. */
export function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  const parts = id.split("_");
  const tail = parts[parts.length - 1] ?? id;
  return tail.slice(-6);
}
