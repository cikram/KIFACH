/** Review and publish a draft procedure — the human gate in the loop. */
import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Play, Save } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useRouter } from "@/lib/router";
import type {
  EvidenceRef,
  OrderingRule,
  SkillGraph,
  Step,
  ValidationResult,
  VideoMeta,
} from "@/types/api";
import { EvidenceViewer, type EvidenceViewerHandle } from "@/components/EvidenceViewer";
import { ProcedureGraph } from "@/components/ProcedureGraph";
import { ProcedureReview } from "@/components/ProcedureReview";
import { Callout, ErrorState, Loading, Panel } from "@/components/Panels";
import { ProvenanceBadge } from "@/components/Badges";

export function ReviewView({ skillId }: { skillId: string }) {
  const { navigate } = useRouter();
  const [skill, setSkill] = useState<SkillGraph | null>(null);
  const [video, setVideo] = useState<VideoMeta | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [highlight, setHighlight] = useState<EvidenceRef | null>(null);
  const player = useRef<EvidenceViewerHandle>(null);

  const load = useCallback(() => {
    api
      .getSkill(skillId)
      .then(async (result) => {
        setSkill(result);
        setError(null);
        if (result.source_video_id) {
          api
            .getVideo(result.source_video_id)
            .then(setVideo)
            .catch(() => setVideo(null));
        }
        setValidation(await api.validateSkill(skillId).catch(() => null));
      })
      .catch((problem) =>
        setError(
          problem instanceof ApiError ? problem.message : "Could not load this procedure.",
        ),
      );
  }, [skillId]);

  useEffect(load, [load]);

  const persist = async (steps: Step[], rules: OrderingRule[]) => {
    if (!skill) return;
    setSkill({ ...skill, steps, rules });
    setSaving(true);
    try {
      const saved = await api.updateSkill(skillId, {
        steps,
        rules,
        confirmed_rule_ids: rules
          .filter((rule) => rule.confirmed_by_expert)
          .map((rule) => rule.rule_id),
        mark_reviewed: true,
      });
      setSkill(saved);
      setValidation(await api.validateSkill(skillId).catch(() => null));
      setError(null);
    } catch (problem) {
      setError(
        problem instanceof ApiError ? problem.message : "Could not save your edits.",
      );
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    setError(null);
    try {
      const response = await api.publishSkill(skillId);
      if (response.skill) {
        setSkill(response.skill);
        setValidation({ ok: true, issues: [] });
      } else {
        setValidation(response.validation);
      }
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Publishing failed.");
    }
  };

  const seek = (evidence: EvidenceRef) => {
    setHighlight(evidence);
    player.current?.seekTo(evidence.t_start);
  };

  if (error && !skill) return <ErrorState message={error} />;
  if (!skill) return <Loading label="Loading procedure…" />;

  const published = skill.status === "published";
  const unconfirmed = (skill.rules ?? []).filter((rule) => !rule.confirmed_by_expert);

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={skill.title}
        subtitle={skill.summary}
        actions={
          <>
            <ProvenanceBadge provenance={skill.provenance ?? "MOCK"} compact />
            <span
              className="chip"
              style={{
                color: published ? "var(--ok)" : "var(--warn)",
                borderColor: published ? "var(--ok)" : "var(--warn)",
              }}
              data-testid="skill-status"
            >
              {skill.status}
            </span>
            {published ? (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate({ name: "practice", skillId })}
                data-testid="go-practice"
              >
                <Play size={15} /> Practice this skill
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void publish()}
                data-testid="publish-skill"
              >
                <CheckCircle2 size={15} /> Publish procedure
              </button>
            )}
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {(skill.validation_flags ?? []).length > 0 && (
            <Callout tone="warn">
              <strong className="text-ink">Needs your attention: </strong>
              {(skill.validation_flags ?? []).join(" ")}
            </Callout>
          )}
          {!published && unconfirmed.length > 0 && (
            <Callout tone="warn">
              {unconfirmed.length} proposed rule
              {unconfirmed.length === 1 ? "" : "s"} still need your confirmation before this
              procedure can be published.
            </Callout>
          )}
          {error && <ErrorState message={error} />}
          <ProcedureGraph skill={skill} height={320} />
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <Panel
          title="Steps and rules"
          subtitle="Edit anything the observer got wrong. Your edits are saved as you make them."
          actions={saving ? <Save size={14} className="animate-pulse" /> : undefined}
        >
          {published ? (
            <div className="flex flex-col gap-3">
              <Callout>
                This procedure is published and locked. Teach a new version to change it.
              </Callout>
              <ol className="flex flex-col gap-2">
                {(skill.steps ?? []).map((step, index) => (
                  <li
                    key={step.step_id}
                    className="rounded-lg border border-line bg-surface-raised p-3"
                  >
                    <p className="text-sm font-medium text-ink">
                      <span className="mono mr-2 text-xs text-ink-faint">{index + 1}</span>
                      {step.title}
                    </p>
                    <p className="mt-1 text-xs text-ink-muted">
                      Checkpoint: {step.checkpoint}
                    </p>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <ProcedureReview
              skill={skill}
              validation={validation}
              saving={saving}
              onChange={(steps, rules) => void persist(steps, rules)}
              onEvidenceClick={seek}
            />
          )}
        </Panel>

        <Panel title="Demonstration" subtitle="Click any evidence thumbnail to seek here.">
          <EvidenceViewer video={video} highlight={highlight} handleRef={player} />
        </Panel>
      </div>
    </div>
  );
}
