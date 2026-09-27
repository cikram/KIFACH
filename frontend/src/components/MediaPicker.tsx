/**
 * Choose the recording to analyse: a file from disk, or one of the bundled
 * samples. The samples are fetched from the app's own /samples path so Demo
 * Mode needs no network and no camera.
 */
import { useRef, useState } from "react";
import { FileVideo, Upload } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { VideoMeta } from "@/types/api";
import { ErrorState, Loading } from "@/components/Panels";
import { SAMPLES, type SampleOption } from "@/lib/samples";

export function MediaPicker({
  onPicked,
  kind,
  busy = false,
}: {
  onPicked: (video: VideoMeta) => void;
  kind: "expert" | "attempt";
  busy?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const options = SAMPLES.filter((sample) =>
    kind === "expert" ? sample.id === "expert" : sample.id !== "expert",
  );

  const upload = async (file: File, scenario?: string) => {
    setError(null);
    setUploading(file.name);
    try {
      onPicked(await api.uploadVideo(file, scenario));
    } catch (problem) {
      setError(
        problem instanceof ApiError
          ? problem.message
          : "The upload failed before it reached the server.",
      );
    } finally {
      setUploading(null);
    }
  };

  const useSample = async (sample: SampleOption) => {
    setError(null);
    setUploading(sample.label);
    try {
      const response = await fetch(`/samples/${sample.file}`);
      if (!response.ok) {
        throw new Error("missing");
      }
      const blob = await response.blob();
      const file = new File([blob], sample.file, { type: "video/webm" });
      onPicked(await api.uploadVideo(file, sample.id));
    } catch (problem) {
      setError(
        problem instanceof ApiError
          ? problem.message
          : `The bundled sample ${sample.file} could not be loaded. Generate the ` +
              "fixtures with: python scripts/make_synthetic_video.py",
      );
    } finally {
      setUploading(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-line bg-surface-sunken px-4 py-6 text-center"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          const file = event.dataTransfer.files?.[0];
          if (file) void upload(file);
        }}
      >
        <Upload size={20} className="text-ink-faint" />
        <div>
          <p className="text-sm font-medium text-ink">
            Drop an .mp4, .mov, or .webm recording here
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            Fixed camera, even lighting, one action at a time. Up to 200 MB.
          </p>
        </div>
        <input
          ref={input}
          type="file"
          accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
          className="sr-only"
          data-testid={`file-input-${kind}`}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            event.target.value = "";
          }}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || Boolean(uploading)}
          onClick={() => input.current?.click()}
        >
          Choose a file
        </button>
      </div>

      <div>
        <p className="label">Or use a bundled sample</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {options.map((sample) => (
            <button
              key={sample.id}
              type="button"
              className="flex items-start gap-2 rounded-lg border border-line bg-surface-raised p-3 text-left hover:border-[var(--accent)] disabled:opacity-50"
              disabled={busy || Boolean(uploading)}
              onClick={() => void useSample(sample)}
              data-testid={`sample-${sample.id}`}
            >
              <FileVideo size={16} className="mt-0.5 shrink-0 text-ink-faint" />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-ink">{sample.label}</span>
                <span className="block text-xs text-ink-muted">{sample.hint}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      {uploading && <Loading label={`Uploading ${uploading}…`} />}
      {error && <ErrorState title="Upload failed" message={error} />}
    </div>
  );
}
