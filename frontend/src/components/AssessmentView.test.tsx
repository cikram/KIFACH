import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AlertFeed, StepChecklist } from "@/components/AssessmentView";
import type { Alert, Observation, SkillGraph } from "@/types/api";

const skill: SkillGraph = {
  skill_id: "skill_1",
  title: "Light an LED",
  steps: [
    { step_id: "led", title: "Seat the LED", checkpoint: "LED in two rows" },
    { step_id: "resistor", title: "Connect the resistor", checkpoint: "resistor bridges" },
  ],
  rules: [],
};

const observation: Observation = {
  observation_id: "o1",
  window_id: "w1",
  step_id: "led",
  status: "completed",
  confidence: 0.88,
  t_start: 2,
  t_end: 3,
  evidence: { video_id: "vid_1", t_start: 2, t_end: 3 },
  rationale: "the LED stands in two rows",
  provenance: "MOCK",
};

describe("the step checklist", () => {
  it("shows each step's state with a word, not only a colour", () => {
    render(
      <StepChecklist
        skill={skill}
        states={{ led: "done", resistor: "skipped" }}
        observations={[observation]}
        onEvidence={() => undefined}
      />,
    );
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText("Skipped")).toBeInTheDocument();
    expect(screen.getByText(/LED in two rows/)).toBeInTheDocument();
  });

  it("hands the evidence reference back when a timestamp is clicked", async () => {
    const onEvidence = vi.fn();
    render(
      <StepChecklist
        skill={skill}
        states={{ led: "done" }}
        observations={[observation]}
        onEvidence={onEvidence}
      />,
    );
    await userEvent.click(screen.getByTestId("evidence-link"));
    expect(onEvidence).toHaveBeenCalledWith(observation.evidence);
  });

  it("falls back to pending for a step with no state yet", () => {
    render(
      <StepChecklist
        skill={skill}
        states={{}}
        observations={[]}
        onEvidence={() => undefined}
      />,
    );
    expect(screen.getAllByText("Not started")).toHaveLength(2);
  });
});

describe("the alert feed", () => {
  const supported: Alert = {
    alert_id: "a1",
    kind: "wrong_order",
    step_id: "power",
    message: "Apply power was performed while the resistor was visibly not done.",
    opened_at: 10,
    opened_evidence: { video_id: "vid_1", t_start: 10, t_end: 11 },
    supported: true,
    resolved: false,
  };

  const unsupported: Alert = {
    alert_id: "a2",
    kind: "prereq_unconfirmed",
    step_id: "resistor",
    message: "The resistor was never confirmed and was not observed absent.",
    opened_at: 14,
    supported: false,
    resolved: false,
  };

  it("separates supported failures from missing evidence", () => {
    render(<AlertFeed alerts={[supported, unsupported]} onEvidence={() => undefined} />);
    expect(screen.getByText("Supported by visible evidence")).toBeInTheDocument();
    expect(screen.getByText(/cannot prove a failure/)).toBeInTheDocument();
  });

  it("marks a corrected alert as resolved", () => {
    render(
      <AlertFeed
        alerts={[{ ...supported, resolved: true, resolved_at: 22 }]}
        onEvidence={() => undefined}
      />,
    );
    expect(screen.getByText("Corrected later in the attempt")).toBeInTheDocument();
  });

  it("says so plainly when there is nothing to report", () => {
    render(<AlertFeed alerts={[]} onEvidence={() => undefined} />);
    expect(screen.getByText("No alerts")).toBeInTheDocument();
  });
});
