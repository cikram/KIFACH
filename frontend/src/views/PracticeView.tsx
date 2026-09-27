/**
 * Practice: assess a learner attempt against a published procedure, streaming
 * the graph, checklist, and alerts as the analysis progresses.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Camera, ListChecks, Workflow } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useRouter } from "@/lib/router";
import { useJobStream } from "@/hooks/useJobStream";
import type {
  Alert,
  EngineEvent,
  EvidenceRef,
  Observation,
  SkillGraph,
  StepState,
  VideoMeta,
} from "@/types/api";
import { AlertFeed, EventLog, StepChecklist } from "@/components/AssessmentView";
import { EvidenceViewer, type EvidenceViewerHandle } from "@/components/EvidenceViewer";
import { MediaPicker } from "@/components/MediaPicker";
import { ProcedureGraph } from "@/components/ProcedureGraph";
import { ErrorState, Loading, Panel } from "@/components/Panels";

export function PracticeView({ skillId }: { skillId: string }) {
  const { navigate } = useRouter();
  const [skill, setSkill] = useState<SkillGraph | null>(null);
  const [video, setVideo] = useState<VideoMeta | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<EvidenceRef | null>(null);
  const [view, setView] = useState<"graph" | "checklist">("graph");
  const player = useRef<EvidenceViewerHandle>(null);

  const job = useJobStream(jobId);

  useEffect(() => {
    api
      .getSkill(skillId)
      .then(setSkill)
      .catch((problem) =>
        setError(
          problem instanceof ApiError ? problem.message : "Could not load the skill.",
        ),
      );
  }, [skillId]);

  const states = useMemo(() => {
    const updates = job.events.filter((event) => event.type === "state_updated");
    const latest = updates[updates.length - 1];
    return (latest?.data.step_states ?? {}) as Record<string, StepState>;
  }, [job.events]);

  const alerts = useMemo(() => {
    const updates = job.events.filter((event) => event.type === "state_updated");
    const latest = updates[updates.length - 1];
    return (latest?.data.alerts ?? []) as Alert[];
  }, [job.events]);

  const observations = useMemo(
    () =>
      job.events
        .filter((event) => event.type === "window_observed")
        .flatMap((event) => (event.data.observations ?? []) as Observation[]),
    [job.events],
  );

  const engineEvents = useMemo(
    () =>
      job.events
        .filter((event) => event.type === "engine_event")
        .map((event) => event.data as unknown as EngineEvent),
    [job.events],
  );

  useEffect(() => {
    if (job.status === "complete" && job.result?.attempt_id) {
      const attemptId = String(job.result.attempt_id);
      const timer = window.setTimeout(() => navigate({ name: "verdict", attemptId }), 1200);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [job.status, job.result, navigate]);

  const start = useCallback(
    async (picked: VideoMeta) => {
      setVideo(picked);
      setError(null);
      try {
        const accepted = await api.startAttempt(skillId, picked.video_id, "upload");
        setJobId(accepted.job_id);
      } catch (problem) {
        setError(
          problem instanceof ApiError
            ? problem.message
            : "Could not start the verification.",
        );
      }
    },
    [skillId],
  );

  const seek = (evidence: EvidenceRef) => {
    setHighlight(evidence);
    player.current?.seekTo(evidence.t_start);
  };

  if (error && !skill) return <ErrorState message={error} />;
  if (!skill) return <Loading label="Loading procedure…" />;

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={`Practice · ${skill.title}`}
        subtitle="Upload an attempt, or use the camera in live mode."
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => navigate({ name: "live", skillId })}
          >
            <Camera size={15} /> Live mode
          </button>
        }
      >
        {!jobId ? (
          <MediaPicker kind="attempt" onPicked={(picked) => void start(picked)} />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {job.status === "running" && <Loading label="Observing the attempt…" />}
            {job.status === "complete" && (
              <p className="text-sm" style={{ color: "var(--ok)" }}>
                Assessment complete. Opening the result…
              </p>
            )}
            <button
              type="button"
              className="btn btn-ghost ml-auto"
              onClick={() => {
                setJobId(null);
                setVideo(null);
              }}
            >
              Start over
            </button>
          </div>
        )}
        {error && <ErrorState message={error} />}
        {job.error && <ErrorState title="Verification failed" message={job.error} />}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <div className="flex flex-col gap-4">
          <Panel
            title="Progress"
            actions={
              <div className="flex gap-1">
                <button
                  type="button"
                  className={`btn btn-ghost ${view === "graph" ? "text-[var(--accent)]" : ""}`}
                  onClick={() => setView("graph")}
                  aria-pressed={view === "graph"}
                >
                  <Workflow size={14} /> Graph
                </button>
                <button
                  type="button"
                  className={`btn btn-ghost ${view === "checklist" ? "text-[var(--accent)]" : ""}`}
                  onClick={() => setView("checklist")}
                  aria-pressed={view === "checklist"}
                >
                  <ListChecks size={14} /> Checklist
                </button>
              </div>
            }
          >
            {view === "graph" ? (
              <ProcedureGraph skill={skill} states={states} height={380} />
            ) : (
              <StepChecklist
                skill={skill}
                states={states}
                observations={observations}
                onEvidence={seek}
              />
            )}
          </Panel>

          <Panel title="Engine events" subtitle="Every decision, in source-time order.">
            <EventLog events={engineEvents} onEvidence={seek} />
          </Panel>
        </div>

        <div className="flex flex-col gap-4">
          <Panel title="Attempt footage">
            <EvidenceViewer video={video} highlight={highlight} handleRef={player} />
          </Panel>
          <Panel title="Alerts">
            <AlertFeed alerts={alerts} onEvidence={seek} />
          </Panel>
          {job.status === "complete" && Boolean(job.result?.attempt_id) && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() =>
                navigate({
                  name: "verdict",
                  attemptId: String(job.result?.attempt_id ?? ""),
                })
              }
            >
              See the result <ArrowRight size={15} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
