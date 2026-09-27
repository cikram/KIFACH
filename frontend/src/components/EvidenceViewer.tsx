/**
 * The evidence surface: a source video that any timestamped reference can seek.
 *
 * Nothing in KIFACH may assert something about an attempt without a way to look
 * at what it was based on, so this component is deliberately dumb and shared:
 * give it a video and a seek target, and it jumps there and says where it is.
 */
import { useEffect, useImperativeHandle, useRef, useState } from "react";
import type { Ref } from "react";
import { Clapperboard, Pause, Play } from "lucide-react";
import type { EvidenceRef, VideoMeta } from "@/types/api";
import { mediaUrl, videoUrl } from "@/lib/api";
import { formatTime } from "@/lib/format";

export interface EvidenceViewerHandle {
  seekTo: (seconds: number) => void;
}

export function EvidenceViewer({
  video,
  highlight,
  handleRef,
  caption,
}: {
  video: VideoMeta | null;
  highlight?: EvidenceRef | null;
  handleRef?: Ref<EvidenceViewerHandle>;
  caption?: string;
}) {
  const videoElement = useRef<HTMLVideoElement>(null);
  const [current, setCurrent] = useState(0);
  const [playing, setPlaying] = useState(false);

  useImperativeHandle(handleRef, () => ({
    seekTo: (seconds: number) => {
      const element = videoElement.current;
      if (!element) return;
      element.currentTime = Math.max(0, seconds);
      void element.play().catch(() => undefined);
    },
  }));

  useEffect(() => {
    const element = videoElement.current;
    if (!element || !highlight) return;
    element.currentTime = Math.max(0, highlight.t_start);
  }, [highlight]);

  const source = videoUrl(video);

  return (
    <figure className="m-0 flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-lg border border-line bg-black">
        {source ? (
          <video
            ref={videoElement}
            src={source}
            controls
            preload="metadata"
            playsInline
            data-testid="evidence-video"
            className="aspect-video w-full bg-black"
            onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        ) : (
          <div className="flex aspect-video w-full items-center justify-center gap-2 text-sm text-ink-faint">
            <Clapperboard size={18} /> No video attached yet
          </div>
        )}
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
        <span className="mono" data-testid="video-position">
          {playing ? (
            <Play size={11} className="inline" />
          ) : (
            <Pause size={11} className="inline" />
          )}{" "}
          {formatTime(current)}
          {video ? ` / ${formatTime(video.duration_s)}` : ""}
        </span>
        {highlight?.note && <span className="truncate">{highlight.note}</span>}
        {caption && <span className="truncate">{caption}</span>}
      </figcaption>
      {highlight?.frame_path && (
        <div className="flex items-center gap-3 rounded-lg border border-line bg-surface-sunken p-2">
          <img
            src={mediaUrl(highlight.frame_path)}
            alt={`Frame at ${formatTime(highlight.t_start)}`}
            className="h-16 w-28 rounded border border-line object-cover"
          />
          <div className="min-w-0 text-xs">
            <p className="mono text-ink">{formatTime(highlight.t_start)}</p>
            <p className="mt-0.5 truncate text-ink-muted">
              {highlight.note ?? "Evidence frame"}
            </p>
          </div>
        </div>
      )}
    </figure>
  );
}
