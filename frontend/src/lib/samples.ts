/** The bundled demo recordings, shared by the picker and Demo Mode. */

export interface SampleOption {
  id: string;
  label: string;
  file: string;
  hint: string;
}

export const SAMPLES: SampleOption[] = [
  {
    id: "expert",
    label: "Expert demonstration",
    file: "expert.webm",
    hint: "The reference run KIFACH learns the procedure from.",
  },
  {
    id: "correct",
    label: "Correct attempt",
    file: "correct.webm",
    hint: "Everything done in a valid order.",
  },
  {
    id: "alternate_order",
    label: "Valid alternate order",
    file: "alternate_order.webm",
    hint: "Independent steps done in a different but acceptable order.",
  },
  {
    id: "wrong_order",
    label: "Wrong order",
    file: "wrong_order.webm",
    hint: "Power applied while the resistor row is visibly empty.",
  },
  {
    id: "uncertain",
    label: "Obscured attempt",
    file: "uncertain.webm",
    hint: "A hand hides the checkpoint; the evidence cannot decide.",
  },
  {
    id: "corrected",
    label: "Wrong order, then corrected",
    file: "corrected.webm",
    hint: "Power removed, resistor added, power reapplied.",
  },
];
