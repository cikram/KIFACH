/**
 * The result: one verdict, the reasons behind it, and clickable evidence for
 * every claim. Uncertainty gets its own treatment — an inconclusive attempt is
 * not a failure, and the screen says so in words.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, RefreshCw, Repeat, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useRouter } from "@/lib/router";
import type { AttemptDetail, EvidenceRef, ReplayResponse, VideoMeta } from "@/types/api";
import { AlertFeed, EventLog, StepChecklist } from "@/components/AssessmentView";
import { EvidenceViewer, type EvidenceViewerHandle } from "@/components/EvidenceViewer";
import { ProcedureGraph } from "@/components/ProcedureGraph";
import { ProvenanceBadge, VerdictBadge } from "@/components/Badges";
import { Callout, ErrorState, Loading, Panel } from "@/components/Panels";
import { VERDICT_MEANING, formatDate } from "@/lib/format";

export function VerdictView({ attemptId }: { attemptId: string }) {
  const { navigate } = useRouter();
  const [detail, setDetail] = useState<AttemptDetail | null>(null);
  const [video, setVideo] = useState<VideoMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [highlight, setHighlight] = useState<EvidenceRef | null>(null);
  const player = useRef<EvidenceViewerHandle>(null);

  const load = useCallback(() => {
    api
      .getAttempt(attemptId)
      .then((result) => {
        setDetail(result);
        setError(null);
        const mediaId = result.attempt.media_id ?? result.attempt.live_session_id;
        if (mediaId) {
          api
            .getVideo(mediaId)
            .then(setVideo)
            .catch(() => setVideo(null));
        }
      })
      .catch((problem) =>
        setError(
          problem instanceof ApiError ? problem.message : "Could not load the attempt.",
        ),
      );
  }, [attemptId]);

  useEffect(load, [load]);

  const seek = (evidence: EvidenceRef) => {
    setHighlight(evidence);
    player.current?.seekTo(evidence.t_start);
  };

  const exportJson = () => {
    if (!detail) return;
    const blob = new Blob([JSON.stringify(detail, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${attemptId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (error && !detail) return <ErrorState message={error} />;
  if (!detail) return <Loading label="Loading result…" />;

  const { attempt, skill } = detail;
  const verdict = attempt.verdict ?? "INCONCLUSIVE";
  const color =
    verdict === "VERIFIED"
      ? "var(--ok)"
      : verdict === "NOT_VERIFIED"
        ? "var(--danger)"
        : "var(--unsure)";

  return (
    <div className="flex flex-col gap-4">
      <section
        className="panel overflow-hidden"
        style={{ borderColor: color }}
        data-testid="verdict-panel"
      >
        <div className="flex flex-col gap-4 p-5 md:flex-row md:items-start">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <VerdictBadge verdict={verdict} large />
              <ProvenanceBadge provenance={attempt.provenance ?? "MOCK"} />
              <span className="mono text-xs text-ink-faint">
                {formatDate(attempt.created_at)} · {attempt.mode ?? "upload"} mode
              </span>
            </div>
            <h1 className="mt-3 text-lg font-semibold text-ink">{skill.title}</h1>
            <p className="mt-1 text-sm text-ink-muted">{VERDICT_MEANING[verdict]}</p>
            <ul className="mt-3 flex flex-col gap-1.5" data-testid="verdict-reasons">
              {(attempt.reasons ?? []).map((reason, index) => (
                <li key={index} className="text-sm text-ink">
                  • {reason}
                </li>
              ))}
            </ul>
            {(attempt.limitations ?? []).length > 0 && (
              <div className="mt-3">
                <Callout tone="warn">
                  <strong className="text-ink">What the footage could not show: </strong>
                  {(attempt.limitations ?? []).join(" ")}
                </Callout>
              </div>
            )}
          </div>
          <div className="flex shrink-0 flex-col gap-2">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate({ name: "practice", skillId: skill.skill_id })}
              data-testid="retry-attempt"
            >
              <Repeat size={15} /> Try again
            </button>
            <button type="button" className="btn" onClick={exportJson}>
              <Download size={15} /> Export JSON
            </button>
            <button
              type="button"
              className="btn"
              onClick={() =>
                api
                  .replayAttempt(attemptId)
                  .then(setReplay)
                  .catch(() => setReplay(null))
              }
              data-testid="replay-attempt"
            >
              <RefreshCw size={15} /> Replay the engine
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate({ name: "home" })}
            >
              Back to library
            </button>
          </div>
        </div>
        {replay && (
          <div
            className="border-t border-line px-5 py-3 text-sm"
            data-testid="replay-result"
          >
            {replay.identical ? (
              <span className="flex items-center gap-2" style={{ color: "var(--ok)" }}>
                <ShieldCheck size={16} />
                Re-running the stored observations reproduced this result exactly:{" "}
                {replay.event_count} events, verdict {replay.verdict}.
              </span>
            ) : (
              <span style={{ color: "var(--danger)" }}>
                The replay differs from the stored result: {replay.differences.join("; ")}
              </span>
            )}
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        <div className="flex flex-col gap-4">
          <Panel title="Steps" subtitle="Click a timestamp to see what the claim rests on.">
            <StepChecklist
              skill={skill}
              states={attempt.step_states ?? {}}
              observations={attempt.observations ?? []}
              onEvidence={seek}
            />
          </Panel>
          <Panel title="Procedure">
            <ProcedureGraph skill={skill} states={attempt.step_states ?? {}} height={340} />
          </Panel>
        </div>

        <div className="flex flex-col gap-4">
          <Panel title="Evidence">
            <EvidenceViewer
              video={video}
              highlight={highlight}
              handleRef={player}
              caption={video ? video.filename : "The recording is no longer available."}
            />
          </Panel>
          <Panel title="Alerts">
            <AlertFeed alerts={attempt.alerts ?? []} onEvidence={seek} />
          </Panel>
          <Panel title="Engine events">
            <EventLog events={attempt.events ?? []} onEvidence={seek} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
