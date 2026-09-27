"""Scripted offline scenarios for the mock provider and the test suite.

These scripts are NOT model output. Everything derived from them is labelled
MOCK end to end. They exist so the loop can be demonstrated and tested with no
network, and so the deterministic engine can be exercised against the five cases
the product has to get right: a valid run, a supported wrong order, an uncertain
attempt, a corrected attempt, and an alternate valid order.

Times are seconds into the source video and line up with the fixtures written by
`scripts/make_synthetic_video.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import ObservationStatus

# Canonical step ids for the reference task. The mock maps these onto whatever
# ids the reviewed procedure actually uses (see mock.map_step_ids).
PLACE_LED = "place_led"
CONNECT_RESISTOR = "connect_resistor"
CONNECT_GROUND = "connect_ground"
APPLY_POWER = "apply_power"
CONFIRM_LED = "confirm_led"

STEP_KEYWORDS: dict[str, tuple[str, ...]] = {
    PLACE_LED: ("place", "insert", "led into", "seat"),
    CONNECT_RESISTOR: ("resistor",),
    CONNECT_GROUND: ("ground", "negative", "black"),
    APPLY_POWER: ("power", "battery", "supply"),
    CONFIRM_LED: ("lit", "light", "confirm", "glow"),
}


@dataclass(frozen=True)
class MockEvent:
    t: float
    step_id: str
    status: ObservationStatus
    confidence: float
    rationale: str


@dataclass(frozen=True)
class MockWindowDesc:
    t_from: float
    t_to: float
    objects: tuple[str, ...]
    actions: tuple[str, ...]
    changes: tuple[str, ...]
    candidate_steps: tuple[str, ...]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    kind: str  # "expert" or "attempt"
    label: str
    expected_verdict: str | None = None
    events: tuple[MockEvent, ...] = ()
    windows: tuple[MockWindowDesc, ...] = ()
    limitations: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# The reference procedure, as the mock would propose it from expert footage.
# ---------------------------------------------------------------------------

PROPOSAL: dict = {
    "title": "Light an LED on a breadboard",
    "summary": (
        "Seat the LED, add a current-limiting resistor, connect ground, apply "
        "power, and confirm the LED lights."
    ),
    "objects": [
        "breadboard",
        "red LED",
        "220 ohm resistor",
        "black jumper wire",
        "red jumper wire",
        "battery pack",
    ],
    "steps": [
        {
            "step_id": PLACE_LED,
            "title": "Seat the LED on the breadboard",
            "action": "Push the LED legs into two separate rows",
            "objects": ["red LED", "breadboard"],
            "description": (
                "The LED sits upright with its longer leg in the row that will "
                "carry power."
            ),
            "checkpoint": "The LED body stands in the breadboard with each leg in its own row",
            "common_mistakes": ["Both legs in the same row", "LED reversed"],
            "required": True,
            "depends_on": [],
        },
        {
            "step_id": CONNECT_RESISTOR,
            "title": "Connect the current-limiting resistor",
            "action": "Bridge the LED's power-side row to the power rail with the resistor",
            "objects": ["220 ohm resistor", "breadboard"],
            "description": (
                "The resistor limits the current through the LED. It must be in "
                "place before the circuit is powered."
            ),
            "checkpoint": "The resistor bridges the LED's power-side row to the red rail",
            "common_mistakes": [
                "Leaving the resistor out",
                "Bridging the wrong two rows",
            ],
            "required": True,
            "depends_on": [PLACE_LED],
        },
        {
            "step_id": CONNECT_GROUND,
            "title": "Connect ground",
            "action": "Run the black jumper from the LED's other row to the ground rail",
            "objects": ["black jumper wire", "breadboard"],
            "description": "This completes the return path of the circuit.",
            "checkpoint": "A black jumper runs from the LED's second row to the blue rail",
            "common_mistakes": ["Using the power rail instead of the ground rail"],
            "required": True,
            "depends_on": [PLACE_LED],
        },
        {
            "step_id": APPLY_POWER,
            "title": "Apply power",
            "action": "Connect the battery pack to the power rail",
            "objects": ["battery pack", "red jumper wire"],
            "description": "Power is applied only once the rest of the circuit is built.",
            "checkpoint": "The red jumper connects the battery pack to the red rail",
            "common_mistakes": ["Powering the board before the resistor is in place"],
            "required": True,
            "depends_on": [CONNECT_GROUND],
        },
        {
            "step_id": CONFIRM_LED,
            "title": "Confirm the LED lights",
            "action": "Look at the LED",
            "objects": ["red LED"],
            "description": "The finished circuit lights the LED steadily.",
            "checkpoint": "The LED is visibly lit",
            "common_mistakes": ["Reporting success while the LED is dark"],
            "required": True,
            "depends_on": [APPLY_POWER],
        },
    ],
    "rules": [
        {
            "rule_id": "rule_resistor_before_power",
            "kind": "safety",
            "before": CONNECT_RESISTOR,
            "after": APPLY_POWER,
            "reason": (
                "Without the current-limiting resistor the LED takes the full "
                "supply current and can be destroyed the moment power is applied."
            ),
        }
    ],
}


EXPERT = Scenario(
    scenario_id="expert",
    kind="expert",
    label="Expert demonstration of the LED circuit",
    windows=(
        MockWindowDesc(
            0.0,
            5.0,
            objects=("breadboard", "red LED", "hand"),
            actions=("a hand lowers the LED towards the breadboard",),
            changes=("the LED goes from the table into the breadboard",),
            candidate_steps=("Seat the LED on the breadboard",),
        ),
        MockWindowDesc(
            5.0,
            9.0,
            objects=("breadboard", "red LED", "220 ohm resistor"),
            actions=("a hand presses a resistor into two rows",),
            changes=("a resistor now bridges the LED row and the red rail",),
            candidate_steps=("Connect the current-limiting resistor",),
        ),
        MockWindowDesc(
            9.0,
            13.0,
            objects=("breadboard", "black jumper wire"),
            actions=("a hand pushes a black wire into the blue rail",),
            changes=("a black jumper now runs to the ground rail",),
            candidate_steps=("Connect ground",),
        ),
        MockWindowDesc(
            13.0,
            17.0,
            objects=("battery pack", "red jumper wire", "breadboard"),
            actions=("a hand connects the battery pack lead to the red rail",),
            changes=("the power lead is now attached",),
            candidate_steps=("Apply power",),
            limitations=("the hand briefly covers the LED",),
        ),
        MockWindowDesc(
            17.0,
            30.0,
            objects=("breadboard", "lit red LED"),
            actions=("the hands withdraw and the LED is shown",),
            changes=("the LED changes from dark to lit",),
            candidate_steps=("Confirm the LED lights",),
        ),
    ),
)


CORRECT = Scenario(
    scenario_id="correct",
    kind="attempt",
    label="Correct learner attempt",
    expected_verdict="VERIFIED",
    events=(
        MockEvent(2.0, PLACE_LED, ObservationStatus.COMPLETED, 0.9,
                  "the LED stands in two separate rows"),
        MockEvent(6.0, CONNECT_RESISTOR, ObservationStatus.COMPLETED, 0.88,
                  "a resistor bridges the LED row and the red rail"),
        # Deliberately inside the overlap of two windows, so the engine has to
        # treat one event described twice as one confirmation.
        MockEvent(9.5, CONNECT_GROUND, ObservationStatus.COMPLETED, 0.86,
                  "a black jumper reaches the blue rail"),
        MockEvent(14.0, APPLY_POWER, ObservationStatus.COMPLETED, 0.87,
                  "the battery lead is attached to the red rail"),
        MockEvent(18.0, CONFIRM_LED, ObservationStatus.COMPLETED, 0.91,
                  "the LED is clearly lit"),
    ),
)


ALTERNATE_ORDER = Scenario(
    scenario_id="alternate_order",
    kind="attempt",
    label="Valid alternate order: resistor before ground",
    expected_verdict="VERIFIED",
    events=(
        MockEvent(2.0, PLACE_LED, ObservationStatus.COMPLETED, 0.9, "LED seated"),
        MockEvent(6.0, CONNECT_GROUND, ObservationStatus.COMPLETED, 0.87,
                  "black jumper reaches the blue rail"),
        MockEvent(10.0, CONNECT_RESISTOR, ObservationStatus.COMPLETED, 0.88,
                  "resistor bridges the LED row and the red rail"),
        MockEvent(14.0, APPLY_POWER, ObservationStatus.COMPLETED, 0.86,
                  "battery lead attached"),
        MockEvent(18.0, CONFIRM_LED, ObservationStatus.COMPLETED, 0.9, "LED lit"),
    ),
)


WRONG_ORDER = Scenario(
    scenario_id="wrong_order",
    kind="attempt",
    label="Power applied before the resistor",
    expected_verdict="NOT_VERIFIED",
    events=(
        MockEvent(2.0, PLACE_LED, ObservationStatus.COMPLETED, 0.9, "LED seated"),
        MockEvent(6.0, CONNECT_GROUND, ObservationStatus.COMPLETED, 0.88,
                  "black jumper reaches the blue rail"),
        # Explicit absence: the row the resistor belongs in is clearly empty.
        MockEvent(9.0, CONNECT_RESISTOR, ObservationStatus.ABSENT, 0.84,
                  "the LED's power-side row is clearly visible and empty"),
        MockEvent(10.0, APPLY_POWER, ObservationStatus.COMPLETED, 0.89,
                  "the battery lead is attached to the red rail"),
        MockEvent(14.0, CONFIRM_LED, ObservationStatus.COMPLETED, 0.82,
                  "the LED is lit"),
    ),
)


UNCERTAIN = Scenario(
    scenario_id="uncertain",
    kind="attempt",
    label="Obscured attempt: the resistor row is never visible",
    expected_verdict="INCONCLUSIVE",
    limitations=("the learner's hand covers the power-side row for most of the clip",),
    events=(
        MockEvent(2.0, PLACE_LED, ObservationStatus.COMPLETED, 0.88, "LED seated"),
        MockEvent(6.0, CONNECT_RESISTOR, ObservationStatus.UNCERTAIN, 0.35,
                  "a hand covers the row where the resistor would go"),
        MockEvent(10.0, CONNECT_GROUND, ObservationStatus.COMPLETED, 0.85,
                  "black jumper reaches the blue rail"),
        MockEvent(14.0, APPLY_POWER, ObservationStatus.COMPLETED, 0.86,
                  "battery lead attached"),
        MockEvent(18.0, CONFIRM_LED, ObservationStatus.UNCERTAIN, 0.4,
                  "glare on the LED; cannot tell whether it is lit"),
    ),
)


CORRECTED = Scenario(
    scenario_id="corrected",
    kind="attempt",
    label="Wrong order, then a real correction",
    expected_verdict="VERIFIED",
    events=(
        MockEvent(2.0, PLACE_LED, ObservationStatus.COMPLETED, 0.9, "LED seated"),
        MockEvent(6.0, CONNECT_GROUND, ObservationStatus.COMPLETED, 0.88,
                  "black jumper reaches the blue rail"),
        MockEvent(9.0, CONNECT_RESISTOR, ObservationStatus.ABSENT, 0.85,
                  "the power-side row is clearly visible and empty"),
        MockEvent(10.0, APPLY_POWER, ObservationStatus.COMPLETED, 0.89,
                  "battery lead attached to the red rail"),
        MockEvent(14.0, APPLY_POWER, ObservationStatus.UNDONE, 0.9,
                  "the battery lead is pulled off the red rail"),
        MockEvent(18.0, CONNECT_RESISTOR, ObservationStatus.COMPLETED, 0.88,
                  "a resistor now bridges the LED row and the red rail"),
        MockEvent(22.0, APPLY_POWER, ObservationStatus.COMPLETED, 0.89,
                  "the battery lead is reattached to the red rail"),
        MockEvent(26.0, CONFIRM_LED, ObservationStatus.COMPLETED, 0.9,
                  "the LED is lit"),
    ),
)


SCENARIOS: dict[str, Scenario] = {
    scenario.scenario_id: scenario
    for scenario in (EXPERT, CORRECT, ALTERNATE_ORDER, WRONG_ORDER, UNCERTAIN, CORRECTED)
}

# Filename fragments that identify a bundled sample when no explicit hint exists.
FILENAME_HINTS: tuple[tuple[str, str], ...] = (
    ("expert", "expert"),
    ("alternate", "alternate_order"),
    ("wrong", "wrong_order"),
    ("corrected", "corrected"),
    ("uncertain", "uncertain"),
    ("correct", "correct"),
)


def scenario_from_filename(filename: str) -> str | None:
    lowered = filename.lower()
    for fragment, scenario_id in FILENAME_HINTS:
        if fragment in lowered:
            return scenario_id
    return None


@dataclass
class ScenarioRegistry:
    """sha256 -> scenario id, written next to the bundled samples."""

    by_hash: dict[str, str] = field(default_factory=dict)

    def lookup(self, sha256: str) -> str | None:
        return self.by_hash.get(sha256)
