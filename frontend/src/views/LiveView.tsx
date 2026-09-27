/**
 * Live mode: the camera streams timestamped frames to the backend, which runs
 * the same observation and engine path as an upload and pushes events back.
 *
 * The session is also recorded locally and uploaded when it ends, so the saved
 * attempt keeps footage that evidence clicks can seek. Upload mode remains the
 * dependable path; this screen states clearly when the camera or provider
 * cannot support a live run.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { CircleDot, Square } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useRouter } from "@/lib/router";
import type { Alert, EngineEvent, SkillGraph, StepState } from "@/types/api";
import { AlertFeed, EventLog } from "@/components/AssessmentView";
import { ProcedureGraph } from "@/components/ProcedureGraph";
import { Callout, ErrorState, Loading, Panel } from "@/components/Panels";

const FRAME_INTERVAL_MS = 500;

export function LiveView({ skillId }: { skillId: string }) {
  const { navigate } = useRouter();
  const [skill, setSkill] = useState<SkillGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "connecting" | "live" | "ended">("idle");
  const [states, setStates] = useState<Record<string, StepState>>({});
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [events, setEvents] = useState<EngineEvent[]>([]);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);

  const socket = useRef<WebSocket | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const preview = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const timer = useRef<number | null>(null);
  const startedAt = useRef<number>(0);
  const attemptIdRef = useRef<string | null>(null);

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

  const cleanup = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    socket.current?.close();
    socket.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const stop = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    socket.current?.send(JSON.stringify({ type: "stop" }));
    recorder.current?.stop();
    recorder.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    setStatus("ended");
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setStatus("connecting");
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    } catch {
      setStatus("idle");
      setError(
        "No camera is available, or permission was denied. Practice from an uploaded " +
          "recording instead — it is the reliable path.",
      );
      return;
    }
    stream.current = media;
    if (preview.current) {
      preview.current.srcObject = media;
      await preview.current.play().catch(() => undefined);
    }

    const chunks: BlobPart[] = [];
    try {
      const capture = new MediaRecorder(media, { mimeType: "video/webm" });
      capture.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      capture.onstop = async () => {
        if (!chunks.length || !attemptIdRef.current) return;
        try {
          const uploaded = await api.uploadVideo(
            new File(
              [new Blob(chunks, { type: "video/webm" })],
              `live-${Date.now()}.webm`,
              {
                type: "video/webm",
              },
            ),
          );
          await api.attachMedia(attemptIdRef.current, uploaded.video_id);
          setNotes((current) => [
            ...current,
            "The session recording was saved as evidence.",
          ]);
        } catch {
          setNotes((current) => [
            ...current,
            "The session recording could not be uploaded, so evidence clicks have no video to seek.",
          ]);
        }
      };
      capture.start();
      recorder.current = capture;
    } catch {
      setNotes((current) => [
        ...current,
        "This browser cannot record the session, so the attempt keeps frames but no video.",
      ]);
    }

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const connection = new WebSocket(
      `${protocol}://${window.location.host}/api/live/${skillId}`,
    );
    socket.current = connection;
    startedAt.current = performance.now();

    connection.onopen = () => {
      setStatus("live");
      timer.current = window.setInterval(() => {
        const element = preview.current;
        const surface = canvas.current;
        if (!element || !surface || connection.readyState !== WebSocket.OPEN) return;
        const width = 640;
        const height = Math.round(
          (element.videoHeight / Math.max(element.videoWidth, 1)) * width,
        );
        surface.width = width;
        surface.height = height || 360;
        const context = surface.getContext("2d");
        if (!context) return;
        context.drawImage(element, 0, 0, surface.width, surface.height);
        const dataUrl = surface.toDataURL("image/jpeg", 0.8);
        connection.send(
          JSON.stringify({
            type: "frame",
            t: (performance.now() - startedAt.current) / 1000,
            jpeg_base64: dataUrl.split(",")[1],
          }),
        );
      }, FRAME_INTERVAL_MS);
    };

    connection.onmessage = (message) => {
      const payload = JSON.parse(message.data as string) as Record<string, unknown>;
      switch (payload.type) {
        case "session_started":
          attemptIdRef.current = String(payload.attempt_id);
          setAttemptId(String(payload.attempt_id));
          break;
        case "state_updated":
          setStates((payload.step_states ?? {}) as Record<string, StepState>);
          setAlerts((payload.alerts ?? []) as Alert[]);
          break;
        case "engine_event":
          setEvents((current) => [...current, payload.event as EngineEvent]);
          break;
        case "window_error":
          setNotes((current) => [...current, String(payload.message)]);
          break;
        case "session_complete":
          setStatus("ended");
          break;
        case "error":
          setError(String(payload.message));
          setStatus("idle");
          break;
        default:
          break;
      }
    };

    connection.onerror = () => {
      setError("The live connection dropped. The attempt kept whatever it had observed.");
      setStatus("ended");
    };
  }, [skillId]);

  if (error && !skill) return <ErrorState message={error} />;
  if (!skill) return <Loading label="Loading procedure…" />;

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={`Live · ${skill.title}`}
        subtitle="Frames are observed in windows, exactly as an uploaded recording is."
        actions={
          status === "live" ? (
            <button
              type="button"
              className="btn"
              style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
              onClick={stop}
            >
              <Square size={14} /> Stop session
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void start()}
              disabled={status === "connecting"}
              data-testid="start-live"
            >
              <CircleDot size={14} /> Start camera session
            </button>
          )
        }
      >
        <div className="flex flex-col gap-3">
          <Callout tone="warn">
            Live mode needs a real provider: the offline mock has no scripted answer for
            your camera. Upload mode is the dependable path for a demo.
          </Callout>
          {error && <ErrorState message={error} />}
          {notes.length > 0 && <Callout>{notes.join(" ")}</Callout>}
          {status === "ended" && attemptId && (
            <button
              type="button"
              className="btn btn-primary self-start"
              onClick={() => navigate({ name: "verdict", attemptId })}
            >
              See the result
            </button>
          )}
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <Panel title="Camera">
          <video
            ref={preview}
            muted
            playsInline
            className="aspect-video w-full rounded-lg border border-line bg-black"
          />
          <canvas ref={canvas} className="hidden" />
          <p className="mt-2 text-xs text-ink-muted">
            {status === "live"
              ? `Streaming at ${(1000 / FRAME_INTERVAL_MS).toFixed(0)} frames per second. Live mode requires more confirmations than upload mode before it calls a step done.`
              : "The camera is not running."}
          </p>
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel title="Progress">
            <ProcedureGraph skill={skill} states={states} height={300} />
          </Panel>
          <Panel title="Alerts">
            <AlertFeed alerts={alerts} onEvidence={() => undefined} />
          </Panel>
          <Panel title="Engine events">
            <EventLog events={events} onEvidence={() => undefined} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
