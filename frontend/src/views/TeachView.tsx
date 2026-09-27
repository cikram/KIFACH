/**
 * Teach: upload or record an expert demonstration, watch the analysis stream,
 * then go to review. Nothing here publishes anything.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Camera, StopCircle } from "lucide-react";
import { api, ApiError, mediaUrl } from "@/lib/api";
import { useRouter } from "@/lib/router";
import { useJobStream } from "@/hooks/useJobStream";
import { formatTime } from "@/lib/format";
import type { HealthResponse, VideoMeta } from "@/types/api";
import { EvidenceViewer } from "@/components/EvidenceViewer";
import { MediaPicker } from "@/components/MediaPicker";
import { Callout, ErrorState, Loading, Panel } from "@/components/Panels";
import { ProvenanceBadge } from "@/components/Badges";

interface WindowRow {
  window_id: string;
  t_start: number;
  t_end: number;
  objects: string[];
  actions: string[];
  changes: string[];
  candidate_steps: string[];
  limitations: string[];
  provenance: string;
}

export function TeachView({ health }: { health: HealthResponse | null }) {
  const { navigate } = useRouter();
  const [video, setVideo] = useState<VideoMeta | null>(null);
  const [taskHint, setTaskHint] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const previewStream = useRef<MediaStream | null>(null);
  const preview = useRef<HTMLVideoElement>(null);

  const job = useJobStream(jobId);

  const windows = useMemo(
    () =>
      job.events
        .filter((event) => event.type === "window_analysed")
        .map((event) => event.data as unknown as WindowRow),
    [job.events],
  );

  const extraction = useMemo(
    () => job.events.find((event) => event.type === "extraction_complete")?.data ?? null,
    [job.events],
  );

  const frames = useMemo(() => {
    const raw = (extraction?.frames ?? []) as { timestamp_s: number; media_path: string }[];
    return raw.filter((_, index) => index % 2 === 0).slice(0, 24);
  }, [extraction]);

  const draftSkillId =
    job.status === "complete" && job.result?.skill_id ? String(job.result.skill_id) : null;

  useEffect(
    () => () => {
      previewStream.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  const startTeach = async () => {
    if (!video) return;
    setError(null);
    try {
      const accepted = await api.teach(video.video_id, taskHint);
      setJobId(accepted.job_id);
    } catch (problem) {
      setError(
        problem instanceof ApiError ? problem.message : "Could not start the analysis.",
      );
    }
  };

  const startRecording = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      previewStream.current = stream;
      if (preview.current) {
        preview.current.srcObject = stream;
        await preview.current.play().catch(() => undefined);
      }
      const chunks: BlobPart[] = [];
      const media = new MediaRecorder(stream, { mimeType: "video/webm" });
      media.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      media.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks, { type: "video/webm" });
        try {
          setVideo(
            await api.uploadVideo(
              new File([blob], `demonstration-${Date.now()}.webm`, {
                type: "video/webm",
              }),
            ),
          );
        } catch (problem) {
          setError(
            problem instanceof ApiError
              ? problem.message
              : "The recording could not be uploaded.",
          );
        }
      };
      recorder.current = media;
      media.start();
      setRecording(true);
    } catch {
      setError(
        "The camera is not available. Grant permission in the browser, or upload a " +
          "recorded file instead.",
      );
    }
  };

  const stopRecording = () => {
    recorder.current?.stop();
    recorder.current = null;
    setRecording(false);
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
      <div className="flex flex-col gap-4">
        <Panel
          title="1 · The expert demonstration"
          subtitle="One short run of the task, filmed from a fixed viewpoint."
        >
          <div className="flex flex-col gap-3">
            <MediaPicker kind="expert" onPicked={setVideo} busy={Boolean(jobId)} />
            <div className="flex flex-wrap items-center gap-2">
              {!recording ? (
                <button type="button" className="btn" onClick={() => void startRecording()}>
                  <Camera size={15} /> Record with the camera
                </button>
              ) : (
                <button
                  type="button"
                  className="btn"
                  style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
                  onClick={stopRecording}
                >
                  <StopCircle size={15} /> Stop and use this recording
                </button>
              )}
            </div>
            <video
              ref={preview}
              muted
              playsInline
              className={`w-full rounded-lg border border-line ${recording ? "" : "hidden"}`}
            />
            {error && <ErrorState message={error} />}
          </div>
        </Panel>

        <Panel
          title="2 · What is this task?"
          subtitle="Optional, one line. It only guides the observer."
        >
          <div className="flex flex-col gap-3">
            <input
              className="field"
              value={taskHint}
              placeholder="e.g. light an LED on a breadboard"
              onChange={(event) => setTaskHint(event.target.value)}
              data-testid="task-hint"
            />
            <button
              type="button"
              className="btn btn-primary self-start"
              disabled={!video || Boolean(jobId)}
              onClick={() => void startTeach()}
              data-testid="start-teach"
            >
              Derive the procedure <ArrowRight size={15} />
            </button>
            {health?.provider.provenance_label === "MOCK" && (
              <Callout tone="warn">
                The mock provider only has scripted output for the bundled samples. Your own
                footage needs a real provider.
              </Callout>
            )}
          </div>
        </Panel>
      </div>

      <div className="flex flex-col gap-4">
        <Panel
          title="Source"
          subtitle={
            video ? `${video.filename} · ${formatTime(video.duration_s)}` : undefined
          }
          actions={
            health && (
              <ProvenanceBadge provenance={health.provider.provenance_label} compact />
            )
          }
        >
          <EvidenceViewer video={video} />
          {frames.length > 0 && (
            <div
              className="mt-3 flex gap-1.5 overflow-x-auto pb-1"
              data-testid="frame-strip"
            >
              {frames.map((frame) => (
                <figure key={frame.media_path} className="m-0 shrink-0">
                  <img
                    src={mediaUrl(frame.media_path)}
                    alt={`Frame at ${formatTime(frame.timestamp_s)}`}
                    className="h-14 w-24 rounded border border-line object-cover"
                  />
                  <figcaption className="mono mt-0.5 text-[10px] text-ink-faint">
                    {formatTime(frame.timestamp_s)}
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Analysis"
          subtitle="What the observer reported in each window, before any procedure exists."
        >
          {!jobId && (
            <p className="text-sm text-ink-muted">
              Pick a demonstration and start the analysis. Progress streams here.
            </p>
          )}
          {jobId && job.status === "running" && (
            <Loading label="Analysing the demonstration…" />
          )}
          {job.error && <ErrorState title="Analysis failed" message={job.error} />}
          {draftSkillId && (
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-sm" style={{ color: "var(--ok)" }}>
                Draft procedure ready. Nothing is published until you review it.
              </p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate({ name: "review", skillId: draftSkillId })}
                data-testid="go-review"
              >
                Review the draft <ArrowRight size={15} />
              </button>
            </div>
          )}
          <ul className="mt-3 flex flex-col gap-2" data-testid="window-list">
            {windows.map((row) => (
              <li
                key={row.window_id}
                className="rounded-lg border border-line bg-surface-raised p-3"
              >
                <div className="flex items-center gap-2">
                  <span className="mono text-xs text-ink-faint">
                    {formatTime(row.t_start)}–{formatTime(row.t_end)}
                  </span>
                  <span className="mono text-[10px] text-ink-faint">{row.provenance}</span>
                </div>
                {row.actions?.length > 0 && (
                  <p className="mt-1 text-sm text-ink">{row.actions.join("; ")}</p>
                )}
                {row.objects?.length > 0 && (
                  <p className="mt-1 text-xs text-ink-muted">
                    Objects: {row.objects.join(", ")}
                  </p>
                )}
                {row.candidate_steps?.length > 0 && (
                  <p className="mt-1 text-xs" style={{ color: "var(--accent)" }}>
                    Possible step: {row.candidate_steps.join(", ")}
                  </p>
                )}
                {row.limitations?.length > 0 && (
                  <p className="mt-1 text-xs" style={{ color: "var(--unsure)" }}>
                    Could not see: {row.limitations.join("; ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
