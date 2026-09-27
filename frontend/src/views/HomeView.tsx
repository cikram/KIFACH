/** The skill library and the product loop in one screen. */
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Camera,
  GraduationCap,
  Trash2,
  Workflow,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useRouter } from "@/lib/router";
import { formatDate, pluralize } from "@/lib/format";
import type { HealthResponse, SkillSummary } from "@/types/api";
import { ProvenanceBadge, VerdictBadge } from "@/components/Badges";
import { EmptyState, ErrorState, Loading, Panel } from "@/components/Panels";
import { Wordmark } from "@/components/Wordmark";

const LOOP = [
  { icon: Camera, title: "Show", detail: "An expert records one short run." },
  {
    icon: Workflow,
    title: "Review",
    detail: "KIFACH drafts a procedure; the expert approves it.",
  },
  {
    icon: GraduationCap,
    title: "Practice",
    detail: "A learner records or streams an attempt.",
  },
  {
    icon: BookOpen,
    title: "Inspect",
    detail: "Every finding links to the footage it rests on.",
  },
];

export function HomeView({ health }: { health: HealthResponse | null }) {
  const { navigate } = useRouter();
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listSkills()
      .then((result) => {
        setSkills(result);
        setError(null);
      })
      .catch((problem) =>
        setError(problem instanceof ApiError ? problem.message : "Could not load skills."),
      );
  }, []);

  useEffect(load, [load]);

  const remove = async (skillId: string, title: string) => {
    if (!window.confirm(`Delete "${title}" and its procedure? Attempts are kept.`)) return;
    try {
      await api.deleteSkill(skillId);
      load();
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Delete failed.");
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <section className="panel overflow-hidden">
        <div className="flex flex-col gap-5 p-6 lg:flex-row lg:items-center">
          <div className="min-w-0 flex-1">
            <Wordmark size={34} withTagline />
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-muted">
              An expert demonstrates a physical task once. KIFACH watches the recording,
              writes down what it actually saw, and proposes a procedure. The expert reviews
              and publishes it. A learner then records an attempt, and a deterministic
              engine assesses it against the published procedure — with every conclusion
              linked to the frame it came from, and an honest answer when the footage cannot
              decide.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate({ name: "teach" })}
                data-testid="cta-teach"
              >
                <Camera size={15} /> Teach a skill
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => navigate({ name: "demo" })}
              >
                Run the offline demo
              </button>
            </div>
          </div>
          <ol className="grid shrink-0 grid-cols-2 gap-3 lg:w-[380px]">
            {LOOP.map((entry, index) => (
              <li
                key={entry.title}
                className="rounded-lg border border-line bg-surface-sunken p-3"
              >
                <entry.icon size={16} className="text-[var(--accent)]" />
                <p className="mt-2 text-sm font-medium text-ink">
                  <span className="mono mr-1 text-xs text-ink-faint">{index + 1}</span>
                  {entry.title}
                </p>
                <p className="mt-1 text-xs text-ink-muted">{entry.detail}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {health?.provider.provenance_label === "MOCK" && (
        <div
          className="rounded-lg border px-4 py-3 text-sm"
          style={{ borderColor: "var(--warn)", background: "var(--surface-raised)" }}
          data-testid="mock-banner"
        >
          <strong className="text-ink">Offline mock provider.</strong>{" "}
          <span className="text-ink-muted">
            Observations come from scripted fixtures, not a model. Set
            <code className="mono mx-1">NVIDIA_API_KEY</code> (or
            <code className="mono mx-1">OPENAI_COMPAT_BASE_URL</code>) and restart to run
            real perception.
          </span>
        </div>
      )}

      <Panel
        title="Skill library"
        subtitle="Draft procedures need review before a learner can be assessed against them."
      >
        {error && <ErrorState message={error} />}
        {!skills && !error && <Loading label="Loading skills…" />}
        {skills?.length === 0 && (
          <EmptyState
            title="No skills yet"
            detail="Teach the first one from an expert recording, or open Demo Mode to watch the whole loop with bundled footage."
            action={
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate({ name: "teach" })}
              >
                Teach a skill <ArrowRight size={14} />
              </button>
            }
          />
        )}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(skills ?? []).map((skill) => (
            <article
              key={skill.skill_id}
              className="flex flex-col gap-3 rounded-lg border border-line bg-surface-raised p-4"
              data-testid="skill-card"
            >
              <div className="flex items-start gap-2">
                <h3 className="min-w-0 flex-1 text-sm font-semibold text-ink">
                  {skill.title}
                </h3>
                <span
                  className="chip"
                  style={{
                    color: skill.status === "published" ? "var(--ok)" : "var(--warn)",
                    borderColor: skill.status === "published" ? "var(--ok)" : "var(--warn)",
                  }}
                >
                  {skill.status}
                </span>
              </div>
              <p className="line-clamp-2 text-xs text-ink-muted">{skill.summary}</p>
              <div className="flex flex-wrap items-center gap-2 text-xs text-ink-faint">
                <span className="mono">{pluralize(skill.step_count, "step")}</span>
                <span className="mono">{pluralize(skill.rule_count, "rule")}</span>
                <span className="mono">{formatDate(skill.created_at)}</span>
                <ProvenanceBadge provenance={skill.provenance ?? "MOCK"} compact />
              </div>
              {skill.last_verdict && (
                <div className="flex items-center gap-2 text-xs text-ink-muted">
                  Last attempt: <VerdictBadge verdict={skill.last_verdict} />
                </div>
              )}
              <div className="mt-auto flex flex-wrap gap-2">
                {skill.status === "draft" ? (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => navigate({ name: "review", skillId: skill.skill_id })}
                    data-testid="review-skill"
                  >
                    Review draft
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() =>
                        navigate({ name: "practice", skillId: skill.skill_id })
                      }
                      data-testid="practice-skill"
                    >
                      Practice
                    </button>
                    <button
                      type="button"
                      className="btn"
                      onClick={() => navigate({ name: "live", skillId: skill.skill_id })}
                    >
                      <Camera size={14} /> Live
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => navigate({ name: "review", skillId: skill.skill_id })}
                    >
                      View procedure
                    </button>
                  </>
                )}
                <button
                  type="button"
                  className="btn btn-ghost ml-auto text-[var(--danger)]"
                  aria-label={`Delete ${skill.title}`}
                  onClick={() => void remove(skill.skill_id, skill.title)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
