/**
 * The one place the frontend talks to the backend.
 *
 * Every response is typed with the generated contract types, and every failure
 * arrives as an ApiError carrying the backend's own code and message, so screens
 * can show something a person can act on instead of a stack trace.
 */
import type {
  Attempt,
  AttemptDetail,
  HealthResponse,
  JobAccepted,
  PublishResponse,
  ReplayResponse,
  SkillGraph,
  SkillSummary,
  SkillUpdate,
  ValidationResult,
  VideoMeta,
} from "@/types/api";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

type ErrorPayload = { error?: { code?: string; message?: string } };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(
      0,
      "network_error",
      "The KIFACH server did not answer. Check that it is running on port 8000.",
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const body = payload as ErrorPayload | null;
    throw new ApiError(
      response.status,
      body?.error?.code ?? "http_error",
      body?.error?.message ?? `The server answered ${response.status}.`,
    );
  }
  return payload as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  providerCheck: () =>
    postJson<{ provider: string; reachable: boolean; detail: string }>(
      "/api/health/provider-check",
      {},
    ),

  uploadVideo: async (file: File, scenario?: string): Promise<VideoMeta> => {
    const form = new FormData();
    form.append("file", file);
    if (scenario) form.append("scenario", scenario);
    return request<VideoMeta>("/api/videos", { method: "POST", body: form });
  },

  getVideo: (videoId: string) => request<VideoMeta>(`/api/videos/${videoId}`),

  teach: (videoId: string, taskHint: string) =>
    postJson<JobAccepted>("/api/skills/teach", {
      video_id: videoId,
      task_hint: taskHint,
    }),

  listSkills: () => request<SkillSummary[]>("/api/skills"),

  getSkill: (skillId: string) => request<SkillGraph>(`/api/skills/${skillId}`),

  validateSkill: (skillId: string) =>
    request<ValidationResult>(`/api/skills/${skillId}/validation`),

  updateSkill: (skillId: string, update: SkillUpdate) =>
    request<SkillGraph>(`/api/skills/${skillId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }),

  publishSkill: (skillId: string) =>
    postJson<PublishResponse>(`/api/skills/${skillId}/publish`, {}),

  deleteSkill: (skillId: string) =>
    request<void>(`/api/skills/${skillId}`, { method: "DELETE" }),

  startAttempt: (skillId: string, videoId: string, mode: "upload" | "live" = "upload") =>
    postJson<JobAccepted>(`/api/skills/${skillId}/attempts`, {
      video_id: videoId,
      mode,
    }),

  getAttempt: (attemptId: string) => request<AttemptDetail>(`/api/attempts/${attemptId}`),

  listAttempts: () => request<Attempt[]>("/api/attempts"),

  replayAttempt: (attemptId: string) =>
    postJson<ReplayResponse>(`/api/attempts/${attemptId}/replay`, {}),

  attachMedia: (attemptId: string, videoId: string) =>
    postJson<Attempt>(`/api/attempts/${attemptId}/media`, { video_id: videoId }),

  jobState: (jobId: string) =>
    request<{
      job_id: string;
      status: string;
      result: Record<string, unknown>;
      error: string | null;
      events: JobEvent[];
    }>(`/api/jobs/${jobId}`),
};

export interface JobEvent {
  id: number;
  type: string;
  at: string;
  data: Record<string, unknown>;
}

export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  return `/api/media/${path.replace(/^\/+/, "")}`;
}

export function videoUrl(video: VideoMeta | null | undefined): string | undefined {
  return mediaUrl(video?.path);
}
