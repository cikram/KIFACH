import { describe, expect, it } from "vitest";
import {
  PROVENANCE_MEANING,
  STEP_STATE_COLOR,
  STEP_STATE_LABEL,
  VERDICT_LABEL,
  VERDICT_MEANING,
  formatDate,
  formatRange,
  formatTime,
  percent,
  pluralize,
  shortId,
} from "@/lib/format";
import { hashFor, parseHash } from "@/lib/routes";

describe("timestamps", () => {
  it("formats source times as mm:ss.s", () => {
    expect(formatTime(0)).toBe("00:00.0");
    expect(formatTime(9.25)).toBe("00:09.3");
    expect(formatTime(75)).toBe("01:15.0");
  });

  it("does not invent a time it does not have", () => {
    expect(formatTime(undefined)).toBe("--:--");
    expect(formatTime(null)).toBe("--:--");
    expect(formatTime(Number.NaN)).toBe("--:--");
  });

  it("clamps negatives rather than printing them", () => {
    expect(formatTime(-4)).toBe("00:00.0");
  });

  it("formats a range", () => {
    expect(formatRange(2, 6)).toBe("00:02.0 – 00:06.0");
  });

  it("falls back for an unparseable date", () => {
    expect(formatDate("not a date")).toBe("—");
    expect(formatDate(null)).toBe("—");
  });
});

describe("labels", () => {
  it("names every step state and verdict", () => {
    for (const state of [
      "pending",
      "in_progress",
      "done",
      "skipped",
      "violation",
      "uncertain",
    ] as const) {
      expect(STEP_STATE_LABEL[state]).toBeTruthy();
      expect(STEP_STATE_COLOR[state]).toMatch(/^var\(--/);
    }
    for (const verdict of ["VERIFIED", "NOT_VERIFIED", "INCONCLUSIVE"] as const) {
      expect(VERDICT_LABEL[verdict]).toBeTruthy();
      expect(VERDICT_MEANING[verdict]).toBeTruthy();
    }
  });

  it("says plainly that mock output is not a model result", () => {
    expect(PROVENANCE_MEANING.MOCK).toMatch(/not a model result/i);
    expect(PROVENANCE_MEANING.CACHED).toMatch(/genuine model response/i);
    expect(PROVENANCE_MEANING.LIVE).toMatch(/live model call/i);
  });

  it("formats counts and confidences", () => {
    expect(percent(0.876)).toBe("88%");
    expect(pluralize(1, "step")).toBe("1 step");
    expect(pluralize(3, "step")).toBe("3 steps");
    expect(shortId("skill_1a0e2f039b5mj9f1u")).toHaveLength(6);
    expect(shortId(null)).toBe("—");
  });
});

describe("routing", () => {
  it("round-trips every screen", () => {
    const routes = [
      { name: "home" },
      { name: "teach" },
      { name: "demo" },
      { name: "review", skillId: "skill_1" },
      { name: "practice", skillId: "skill_1" },
      { name: "live", skillId: "skill_1" },
      { name: "verdict", attemptId: "att_1" },
    ] as const;
    for (const route of routes) {
      expect(parseHash(hashFor(route))).toEqual(route);
    }
  });

  it("falls back home for anything unrecognised", () => {
    expect(parseHash("#/nonsense")).toEqual({ name: "home" });
    expect(parseHash("")).toEqual({ name: "home" });
    expect(parseHash("#/review")).toEqual({ name: "home" });
  });
});
