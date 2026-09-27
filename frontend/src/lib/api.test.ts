import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, mediaUrl } from "@/lib/api";

function stubFetch(response: Response | Error) {
  const mock = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the API client", () => {
  it("returns parsed payloads", async () => {
    stubFetch(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await expect(api.health()).resolves.toEqual({ status: "ok" });
  });

  it("surfaces the backend's own error code and message", async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          error: { code: "skill_not_published", message: "Publish it first." },
        }),
        { status: 409 },
      ),
    );
    const failure = await api.startAttempt("skill_1", "vid_1").catch((error) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("skill_not_published");
    expect((failure as ApiError).message).toBe("Publish it first.");
    expect((failure as ApiError).status).toBe(409);
  });

  it("explains a dead server instead of throwing a TypeError", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    const failure = await api.listSkills().catch((error) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("network_error");
    expect((failure as ApiError).message).toMatch(/port 8000/);
  });

  it("copes with an error body that is not JSON", async () => {
    stubFetch(new Response("<html>502</html>", { status: 502 }));
    const failure = await api.listSkills().catch((error) => error);
    expect((failure as ApiError).status).toBe(502);
    expect((failure as ApiError).code).toBe("http_error");
  });

  it("handles an empty 204 body", async () => {
    stubFetch(new Response(null, { status: 204 }));
    await expect(api.deleteSkill("skill_1")).resolves.toBeUndefined();
  });

  it("sends uploads as multipart with the scenario tag", async () => {
    const mock = stubFetch(new Response(JSON.stringify({ video_id: "vid_1" })));
    await api.uploadVideo(new File(["x"], "clip.webm", { type: "video/webm" }), "correct");
    const call = mock.mock.calls[0] as unknown as [string, RequestInit];
    const init = call[1];
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("scenario")).toBe("correct");
  });
});

describe("media urls", () => {
  it("routes media through the API", () => {
    expect(mediaUrl("vid_1/frames/f0.jpg")).toBe("/api/media/vid_1/frames/f0.jpg");
    expect(mediaUrl("/vid_1/frames/f0.jpg")).toBe("/api/media/vid_1/frames/f0.jpg");
  });

  it("returns nothing for a missing path", () => {
    expect(mediaUrl(null)).toBeUndefined();
    expect(mediaUrl(undefined)).toBeUndefined();
  });
});
