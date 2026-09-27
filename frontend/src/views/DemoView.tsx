/**
 * Demo Mode: the whole loop with bundled footage and the scripted offline
 * provider. It is labelled MOCK on every panel — nothing here is a model
 * result, and the screen says so before it says anything else.
 */
import { useCallback, useMemo, useState } from "react";
import { ArrowRight, FlaskConical, Play } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useRouter } from "@/lib/router";
import { useJobStream } from "@/hooks/useJobStream";
import { SAMPLES } from "@/lib/samples";
import { ProvenanceBadge } from "@/components/Badges";
import { Callout, ErrorState, Loading, Panel } from "@/components/Panels";
import type { HealthResponse, SkillGraph } from "@/types/api";

type Stage = "idle" | "teaching" | "review" | "verifying";

export function DemoView({ health }: { health: HealthResponse | null }) {
  const { navigate } = useRouter();
  const [stage, setStage] = useState<Stage>("idle");
  const [skill, setSkill] = useState<SkillGraph | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);

  const job = useJobStream(jobId);
  const isMock = health?.provider.provenance_label === "MOCK";

  const note = useCallback((line: string) => setLog((current) => [...current, line]), []);

  const uploadSample = useCallback(async (scenarioId: string, file: string) => {
    const response = await fetch(`/samples/${file}`);
    if (!response.ok) {
      throw new ApiError(
        404,
        "sample_missing",
        `The bundled sample ${file} is not present. Generate the fixtures with: python scripts/make_synthetic_video.py`,
      );
    }
    const blob = await response.blob();
    return api.uploadVideo(new File([blob], file, { type: "video/webm" }), scenarioId);
  }, []);

  const teach = useCallback(async () => {
    setError(null);
    setStage("teaching");
    setLog([]);
    try {
      note("Uploading the expert demonstration…");
      const video = await uploadSample("expert", "expert.webm");
      note(`Stored as ${video.video_id} (${video.duration_s.toFixed(1)}s).`);
      const accepted = await api.teach(video.video_id, "light an LED on a breadboard");
      setJobId(accepted.job_id);
      note("Observing the demonstration window by window…");
    } catch (problem) {
      setStage("idle");
      setError(problem instanceof ApiError ? problem.message : "The demo could not start.");
    }
  }, [note, uploadSample]);

  const reviewAndPublish = useCallback(async () => {
    const skillId = String(job.result?.skill_id ?? "");
    if (!skillId) return;
    try {
      const draft = await api.getSkill(skillId);
      note(
        `Draft ready: ${(draft.steps ?? []).length} steps and ${(draft.rules ?? []).length} proposed rule(s).`,
      );
      const saved = await api.updateSkill(skillId, {
        confirmed_rule_ids: (draft.rules ?? []).map((rule) => rule.rule_id),
        mark_reviewed: true,
        reviewer_note: "Confirmed in Demo Mode.",
      });
      note("Expert confirmed the resistor-before-power rule.");
      const published = await api.publishSkill(saved.skill_id);
      if (!published.skill) {
        setError(
          (published.validation.issues ?? []).map((issue) => issue.message).join(" "),
        );
        return;
      }
      setSkill(published.skill);
      setStage("review");
      note("Procedure published. A learner can now be assessed against it.");
    } catch (problem) {
      setError(problem instanceof ApiError ? problem.message : "Review failed.");
    }
  }, [job.result, note]);

  const runScenario = useCallback(
    async (scenarioId: string, file: string) => {
      if (!skill) return;
      setError(null);
      setStage("verifying");
      try {
        const video = await uploadSample(scenarioId, file);
        const accepted = await api.startAttempt(skill.skill_id, video.video_id, "upload");
        setJobId(accepted.job_id);
        note(`Verifying the ${scenarioId.replace("_", " ")} attempt…`);
      } catch (problem) {
        setStage("review");
        setError(problem instanceof ApiError ? problem.message : "Verification failed.");
      }
    },
    [note, skill, uploadSample],
  );

  const attemptId = useMemo(() => {
    if (stage !== "verifying" || job.status !== "complete") return null;
    return job.result?.attempt_id ? String(job.result.attempt_id) : null;
  }, [job.result, job.status, stage]);

  const teachReady = stage === "teaching" && job.status === "complete";

  return (
    <div className="flex flex-col gap-4">
      <section
        className="panel p-5"
        style={{ borderColor: isMock ? "var(--warn)" : "var(--line)" }}
        data-testid="demo-banner"
      >
        <div className="flex flex-wrap items-center gap-3">
          <FlaskConical size={18} style={{ color: "var(--warn)" }} />
          <h1 className="text-base font-semibold text-ink">
            Demo Mode — offline and scripted
          </h1>
          <ProvenanceBadge provenance={health?.provider.provenance_label ?? "MOCK"} />
        </div>
        <p className="mt-2 max-w-3xl text-sm text-ink-muted">
          This runs the complete loop with bundled synthetic footage and the scripted
          offline provider. The observations are fixtures, not model output, and every
          screen in this run is labelled accordingly. The deterministic engine, the review
          gate, the evidence links, and the verdicts are the real ones.
        </p>
        {!isMock && (
          <div className="mt-3">
            <Callout tone="warn">
              A real provider is configured, so these runs will make live model calls and be
              labelled LIVE or CACHED rather than MOCK.
            </Callout>
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="1 · Teach from the expert demonstration">
          <div className="flex flex-col gap-3">
            <button
              type="button"
              className="btn btn-primary self-start"
              onClick={() => void teach()}
              disabled={stage === "teaching" && job.status === "running"}
              data-testid="demo-teach"
            >
              <Play size={15} /> Run the teach step
            </button>
            {stage === "teaching" && job.status === "running" && (
              <Loading label="Observing and drafting…" />
            )}
            {teachReady && !skill && (
              <button
                type="button"
                className="btn btn-primary self-start"
                onClick={() => void reviewAndPublish()}
                data-testid="demo-publish"
              >
                2 · Confirm the safety rule and publish <ArrowRight size={15} />
              </button>
            )}
            {skill && (
              <p className="text-sm" style={{ color: "var(--ok)" }}>
                Published: {skill.title}
              </p>
            )}
          </div>
        </Panel>

        <Panel
          title="3 · Assess learner attempts"
          subtitle="Each one exercises a different outcome."
        >
          <div className="grid gap-2">
            {SAMPLES.filter((sample) => sample.id !== "expert").map((sample) => (
              <button
                key={sample.id}
                type="button"
                className="flex items-start gap-2 rounded-lg border border-line bg-surface-raised p-3 text-left hover:border-[var(--accent)] disabled:opacity-50"
                disabled={!skill || (stage === "verifying" && job.status === "running")}
                onClick={() => void runScenario(sample.id, sample.file)}
                data-testid={`demo-run-${sample.id}`}
              >
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-ink">{sample.label}</span>
                  <span className="block text-xs text-ink-muted">{sample.hint}</span>
                </span>
              </button>
            ))}
          </div>
          {stage === "verifying" && job.status === "running" && (
            <div className="mt-3">
              <Loading label="Observing the attempt…" />
            </div>
          )}
          {attemptId && (
            <button
              type="button"
              className="btn btn-primary mt-3"
              onClick={() => navigate({ name: "verdict", attemptId })}
              data-testid="demo-see-result"
            >
              See the result <ArrowRight size={15} />
            </button>
          )}
        </Panel>
      </div>

      <Panel title="Demo log">
        {error && <ErrorState message={error} />}
        {job.error && <ErrorState title="The job failed" message={job.error} />}
        <ol className="flex flex-col gap-1 text-sm text-ink-muted">
          {log.map((line, index) => (
            <li key={index} className="mono text-xs">
              {line}
            </li>
          ))}
          {log.length === 0 && <li>Nothing yet. Start with the teach step.</li>}
        </ol>
      </Panel>
    </div>
  );
}
