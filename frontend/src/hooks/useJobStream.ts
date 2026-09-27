/**
 * Follow a backend job over SSE.
 *
 * The stream is resumable: the hook remembers the last event id it saw and asks
 * for everything after it, and it falls back to a one-shot GET of the job state
 * if the stream cannot be opened at all. A refreshed page therefore recovers the
 * progress it missed instead of showing an empty screen.
 */
import { useEffect, useRef, useState } from "react";
import { api, type JobEvent } from "@/lib/api";

export interface JobStream {
  events: JobEvent[];
  status: "idle" | "running" | "complete" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
}

export function useJobStream(jobId: string | null): JobStream {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [status, setStatus] = useState<JobStream["status"]>("idle");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastId = useRef(0);

  useEffect(() => {
    if (!jobId) {
      setEvents([]);
      setStatus("idle");
      setResult(null);
      setError(null);
      lastId.current = 0;
      return;
    }

    let cancelled = false;
    setStatus("running");
    setEvents([]);
    setResult(null);
    setError(null);
    lastId.current = 0;

    const source = new EventSource(`/api/jobs/${jobId}/events?last_event_id=0`);

    const handle = (raw: MessageEvent<string>) => {
      if (cancelled) return;
      let event: JobEvent;
      try {
        event = JSON.parse(raw.data) as JobEvent;
      } catch {
        return;
      }
      if (event.type === "ping") return;
      lastId.current = Math.max(lastId.current, event.id);
      setEvents((previous) =>
        previous.some((existing) => existing.id === event.id)
          ? previous
          : [...previous, event],
      );
      if (event.type === "complete") {
        setResult(event.data);
        setStatus("complete");
        source.close();
      }
      if (event.type === "error") {
        setError(String(event.data.message ?? "The job failed."));
        setStatus("failed");
        source.close();
      }
    };

    source.onmessage = handle;
    for (const type of [
      "extraction_started",
      "extraction_complete",
      "window_analysed",
      "window_observed",
      "proposal_started",
      "validation_repairing",
      "validation_complete",
      "engine_event",
      "state_updated",
      "attempt_created",
      "complete",
      "error",
    ]) {
      source.addEventListener(type, handle as EventListener);
    }

    source.onerror = () => {
      if (cancelled) return;
      // The stream dropped. Recover the authoritative state once.
      api
        .jobState(jobId)
        .then((state) => {
          if (cancelled) return;
          setEvents(state.events);
          if (state.status === "complete") {
            setResult(state.result);
            setStatus("complete");
            source.close();
          } else if (state.status === "failed") {
            setError(state.error ?? "The job failed.");
            setStatus("failed");
            source.close();
          }
        })
        .catch(() => undefined);
    };

    return () => {
      cancelled = true;
      source.close();
    };
  }, [jobId]);

  return { events, status, result, error };
}
