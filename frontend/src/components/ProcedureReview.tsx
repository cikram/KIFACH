/**
 * The expert review editor.
 *
 * A draft arrives as a model proposal and cannot leave this screen until a human
 * has looked at it: every rule must be confirmed or removed, every step needs a
 * checkpoint, and the dependency graph must stay acyclic. The UI keeps saying
 * which parts are still only proposals until they are confirmed.
 */
import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import type {
  EvidenceRef,
  OrderingRule,
  SkillGraph,
  Step,
  ValidationResult,
} from "@/types/api";
import { mediaUrl } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { ProposedBadge } from "@/components/Badges";
import { Callout, ErrorState } from "@/components/Panels";

interface Props {
  skill: SkillGraph;
  validation: ValidationResult | null;
  saving: boolean;
  onChange: (steps: Step[], rules: OrderingRule[]) => void;
  onEvidenceClick?: (evidence: EvidenceRef) => void;
}

export function ProcedureReview({
  skill,
  validation,
  saving,
  onChange,
  onEvidenceClick,
}: Props) {
  const steps = skill.steps ?? [];
  const rules = skill.rules ?? [];
  const [open, setOpen] = useState<string | null>(steps[0]?.step_id ?? null);

  const issuesByStep = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const issue of validation?.issues ?? []) {
      if (!issue.step_id) continue;
      map.set(issue.step_id, [...(map.get(issue.step_id) ?? []), issue.message]);
    }
    return map;
  }, [validation]);

  const updateStep = (stepId: string, patch: Partial<Step>) => {
    onChange(
      steps.map((step) => (step.step_id === stepId ? { ...step, ...patch } : step)),
      rules,
    );
  };

  const removeStep = (stepId: string) => {
    onChange(
      steps
        .filter((step) => step.step_id !== stepId)
        .map((step) => ({
          ...step,
          depends_on: (step.depends_on ?? []).filter((id) => id !== stepId),
        })),
      rules.filter((rule) => rule.before !== stepId && rule.after !== stepId),
    );
  };

  const toggleDependency = (stepId: string, dependency: string) => {
    const step = steps.find((candidate) => candidate.step_id === stepId);
    if (!step) return;
    const current = step.depends_on ?? [];
    updateStep(stepId, {
      depends_on: current.includes(dependency)
        ? current.filter((id) => id !== dependency)
        : [...current, dependency],
    });
  };

  const confirmRule = (ruleId: string) => {
    onChange(
      steps,
      rules.map((rule) =>
        rule.rule_id === ruleId ? { ...rule, confirmed_by_expert: true } : rule,
      ),
    );
  };

  const removeRule = (ruleId: string) => {
    onChange(
      steps,
      rules.filter((rule) => rule.rule_id !== ruleId),
    );
  };

  const addStep = () => {
    const id = `step_${steps.length + 1}_${Math.random().toString(36).slice(2, 6)}`;
    onChange(
      [
        ...steps,
        {
          step_id: id,
          title: "New step",
          action: "",
          objects: [],
          description: "",
          checkpoint: "",
          common_mistakes: [],
          required: true,
          depends_on: [],
          evidence: [],
          proposed_by_model: false,
        },
      ],
      rules,
    );
    setOpen(id);
  };

  return (
    <div className="flex flex-col gap-4">
      {validation && !validation.ok && (
        <ErrorState
          title="This procedure cannot be published yet"
          message={(validation.issues ?? []).map((issue) => issue.message).join(" ")}
        />
      )}

      <div className="flex flex-col gap-2">
        {steps.map((step, index) => {
          const expanded = open === step.step_id;
          const problems = issuesByStep.get(step.step_id) ?? [];
          return (
            <article
              key={step.step_id}
              className="rounded-lg border border-line bg-surface-raised"
              data-testid="review-step"
            >
              <button
                type="button"
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
                onClick={() => setOpen(expanded ? null : step.step_id)}
                aria-expanded={expanded}
              >
                {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                <span className="mono text-xs text-ink-faint">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
                  {step.title}
                </span>
                {step.proposed_by_model && (
                  <span className="chip border-line text-ink-muted">proposed</span>
                )}
                {!step.checkpoint?.trim() && (
                  <span
                    className="chip"
                    style={{ color: "var(--warn)", borderColor: "var(--warn)" }}
                  >
                    needs checkpoint
                  </span>
                )}
                {problems.length > 0 && (
                  <span
                    className="chip"
                    style={{ color: "var(--danger)", borderColor: "var(--danger)" }}
                  >
                    {problems.length} problem{problems.length === 1 ? "" : "s"}
                  </span>
                )}
              </button>

              {expanded && (
                <div className="grid gap-3 border-t border-line p-3 md:grid-cols-2">
                  <div className="md:col-span-2">
                    <label className="label" htmlFor={`title-${step.step_id}`}>
                      Title
                    </label>
                    <input
                      id={`title-${step.step_id}`}
                      className="field"
                      value={step.title}
                      onChange={(event) =>
                        updateStep(step.step_id, { title: event.target.value })
                      }
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor={`action-${step.step_id}`}>
                      Action
                    </label>
                    <input
                      id={`action-${step.step_id}`}
                      className="field"
                      value={step.action ?? ""}
                      onChange={(event) =>
                        updateStep(step.step_id, { action: event.target.value })
                      }
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor={`objects-${step.step_id}`}>
                      Objects (comma separated)
                    </label>
                    <input
                      id={`objects-${step.step_id}`}
                      className="field"
                      value={(step.objects ?? []).join(", ")}
                      onChange={(event) =>
                        updateStep(step.step_id, {
                          objects: event.target.value
                            .split(",")
                            .map((value) => value.trim())
                            .filter(Boolean),
                        })
                      }
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="label" htmlFor={`checkpoint-${step.step_id}`}>
                      Checkpoint — what a reviewer must see for this step to count
                    </label>
                    <input
                      id={`checkpoint-${step.step_id}`}
                      className="field"
                      value={step.checkpoint ?? ""}
                      placeholder="e.g. the resistor bridges the LED row and the red rail"
                      onChange={(event) =>
                        updateStep(step.step_id, { checkpoint: event.target.value })
                      }
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="label" htmlFor={`description-${step.step_id}`}>
                      Description
                    </label>
                    <textarea
                      id={`description-${step.step_id}`}
                      className="field min-h-[68px]"
                      value={step.description ?? ""}
                      onChange={(event) =>
                        updateStep(step.step_id, { description: event.target.value })
                      }
                    />
                  </div>

                  <fieldset className="md:col-span-2">
                    <legend className="label">Must happen after</legend>
                    <div className="flex flex-wrap gap-2">
                      {steps
                        .filter((candidate) => candidate.step_id !== step.step_id)
                        .map((candidate) => {
                          const active = (step.depends_on ?? []).includes(
                            candidate.step_id,
                          );
                          return (
                            <label
                              key={candidate.step_id}
                              className={`chip cursor-pointer ${
                                active
                                  ? "border-[var(--accent)] text-[var(--accent)]"
                                  : "border-line text-ink-muted"
                              }`}
                            >
                              <input
                                type="checkbox"
                                className="sr-only"
                                checked={active}
                                onChange={() =>
                                  toggleDependency(step.step_id, candidate.step_id)
                                }
                              />
                              {candidate.title}
                            </label>
                          );
                        })}
                    </div>
                  </fieldset>

                  <div className="flex items-center gap-3 md:col-span-2">
                    <label className="flex items-center gap-2 text-sm text-ink-muted">
                      <input
                        type="checkbox"
                        checked={step.required ?? true}
                        onChange={(event) =>
                          updateStep(step.step_id, { required: event.target.checked })
                        }
                      />
                      Required for a pass
                    </label>
                    <button
                      type="button"
                      className="btn btn-ghost ml-auto text-[var(--danger)]"
                      onClick={() => removeStep(step.step_id)}
                    >
                      <Trash2 size={14} /> Remove step
                    </button>
                  </div>

                  {(step.evidence ?? []).length > 0 && (
                    <div className="md:col-span-2">
                      <p className="label">Evidence from the demonstration</p>
                      <div className="flex flex-wrap gap-2">
                        {(step.evidence ?? []).map((evidence, evidenceIndex) => (
                          <button
                            key={`${step.step_id}-${evidenceIndex}`}
                            type="button"
                            className="overflow-hidden rounded border border-line"
                            onClick={() => onEvidenceClick?.(evidence)}
                            title={`Seek to ${formatTime(evidence.t_start)}`}
                          >
                            {evidence.frame_path ? (
                              <img
                                src={mediaUrl(evidence.frame_path)}
                                alt={`Evidence at ${formatTime(evidence.t_start)}`}
                                className="h-14 w-24 object-cover"
                              />
                            ) : (
                              <span className="mono block px-2 py-3 text-xs">
                                {formatTime(evidence.t_start)}
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {problems.length > 0 && (
                    <div className="md:col-span-2">
                      <Callout tone="warn">{problems.join(" ")}</Callout>
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>

      <button type="button" className="btn self-start" onClick={addStep}>
        <Plus size={14} /> Add a step
      </button>

      <section className="rounded-lg border border-line bg-surface-raised">
        <header className="border-b border-line px-3 py-2">
          <h3 className="text-sm font-semibold text-ink">Ordering and safety rules</h3>
          <p className="mt-0.5 text-xs text-ink-muted">
            The model proposes these. Nothing is enforced against a learner until you
            confirm it.
          </p>
        </header>
        <div className="flex flex-col gap-2 p-3">
          {rules.length === 0 && (
            <p className="text-sm text-ink-muted">No ordering rules in this procedure.</p>
          )}
          {rules.map((rule) => {
            const before = steps.find((step) => step.step_id === rule.before);
            const after = steps.find((step) => step.step_id === rule.after);
            return (
              <div
                key={rule.rule_id}
                className="flex flex-wrap items-start gap-3 rounded-lg border border-line p-3"
                data-testid="review-rule"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink">
                    <strong>{before?.title ?? rule.before}</strong> must happen before{" "}
                    <strong>{after?.title ?? rule.after}</strong>
                  </p>
                  <p className="mt-1 text-sm text-ink-muted">{rule.reason}</p>
                </div>
                <ProposedBadge confirmed={rule.confirmed_by_expert ?? false} />
                {!rule.confirmed_by_expert && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => confirmRule(rule.rule_id)}
                    data-testid="confirm-rule"
                  >
                    Confirm rule
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-ghost text-[var(--danger)]"
                  onClick={() => removeRule(rule.rule_id)}
                >
                  <Trash2 size={14} /> Remove
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {saving && <p className="text-xs text-ink-muted">Saving your edits…</p>}
    </div>
  );
}
