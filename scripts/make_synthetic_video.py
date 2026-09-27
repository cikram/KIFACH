"""Generate deterministic WebM fixtures for tests and offline Demo Mode.

These are drawings, not recordings: a top-down breadboard, an LED, a resistor,
two jumper wires, and a battery pack, animated so each scenario's timeline
matches the scripted mock observations in
`backend/app/providers/scenarios.py`. They exist so the loop can be tested and
demonstrated with no camera and no network.

They are NOT a substitute for real footage. Validating perception quality needs
real video; see samples/RECORDING_GUIDE.md.

Usage:
    python scripts/make_synthetic_video.py            # write all scenarios
    python scripts/make_synthetic_video.py --only correct
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = REPO_ROOT / "samples"

FPS = 12
WIDTH, HEIGHT = 960, 540

# Palette (BGR)
BG = (38, 34, 30)
BOARD = (196, 202, 208)
BOARD_EDGE = (120, 126, 132)
RAIL_RED = (60, 60, 210)
RAIL_BLUE = (200, 120, 40)
LED_OFF = (70, 70, 110)
LED_ON = (90, 90, 255)
RESISTOR = (120, 170, 210)
WIRE_BLACK = (28, 28, 28)
WIRE_RED = (50, 50, 205)
BATTERY = (80, 96, 110)
HAND = (150, 170, 200)
TEXT = (235, 238, 240)


@dataclass(frozen=True)
class Timeline:
    """When each visible element appears, in seconds."""

    duration: float
    led_placed: float | None = None
    resistor_in: float | None = None
    resistor_out: float | None = None  # removed again at this time
    ground_in: float | None = None
    power_in: float | None = None
    power_out: float | None = None
    power_back: float | None = None
    led_lit: float | None = None
    occlude: tuple[tuple[float, float], ...] = ()
    caption: str = ""


SCENARIOS: dict[str, Timeline] = {
    "expert": Timeline(
        duration=24.0,
        led_placed=2.0,
        resistor_in=6.0,
        ground_in=10.0,
        power_in=14.0,
        led_lit=17.5,
        occlude=((13.4, 14.6),),
        caption="EXPERT DEMONSTRATION",
    ),
    "correct": Timeline(
        duration=22.0,
        led_placed=2.0,
        resistor_in=6.0,
        ground_in=9.5,
        power_in=14.0,
        led_lit=18.0,
        caption="LEARNER ATTEMPT",
    ),
    "alternate_order": Timeline(
        duration=22.0,
        led_placed=2.0,
        ground_in=6.0,
        resistor_in=10.0,
        power_in=14.0,
        led_lit=18.0,
        caption="LEARNER ATTEMPT",
    ),
    "wrong_order": Timeline(
        duration=18.0,
        led_placed=2.0,
        ground_in=6.0,
        power_in=10.0,
        led_lit=14.0,
        caption="LEARNER ATTEMPT",
    ),
    "uncertain": Timeline(
        duration=22.0,
        led_placed=2.0,
        resistor_in=6.0,
        ground_in=10.0,
        power_in=14.0,
        led_lit=18.0,
        occlude=((5.0, 8.0), (17.0, 20.0)),
        caption="LEARNER ATTEMPT",
    ),
    "corrected": Timeline(
        duration=30.0,
        led_placed=2.0,
        ground_in=6.0,
        power_in=10.0,
        power_out=14.0,
        resistor_in=18.0,
        power_back=22.0,
        led_lit=26.0,
        caption="LEARNER ATTEMPT",
    ),
}


def active(at: float | None, t: float) -> bool:
    return at is not None and t >= at


def draw_frame(timeline: Timeline, t: float) -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH, 3), BG, dtype=np.uint8)

    # Breadboard
    board = (180, 120, 780, 430)
    cv2.rectangle(frame, board[:2], board[2:], BOARD, -1)
    cv2.rectangle(frame, board[:2], board[2:], BOARD_EDGE, 2)
    for x in range(200, 780, 24):
        for y in range(180, 420, 24):
            cv2.circle(frame, (x, y), 3, BOARD_EDGE, -1)
    # Rails
    cv2.rectangle(frame, (180, 132), (780, 150), RAIL_RED, -1)
    cv2.rectangle(frame, (180, 400), (780, 418), RAIL_BLUE, -1)
    cv2.putText(frame, "+", (160, 148), cv2.FONT_HERSHEY_SIMPLEX, 0.7, RAIL_RED, 2)
    cv2.putText(frame, "-", (162, 415), cv2.FONT_HERSHEY_SIMPLEX, 0.7, RAIL_BLUE, 2)

    power_on = (
        active(timeline.power_in, t)
        and not (timeline.power_out is not None and t >= timeline.power_out
                 and not (timeline.power_back is not None and t >= timeline.power_back))
    )

    # Resistor sits in the row left of the LED, so both stay visible.
    resistor_present = active(timeline.resistor_in, t) and not (
        timeline.resistor_out is not None and t >= timeline.resistor_out
    )
    if resistor_present:
        cv2.line(frame, (348, 150), (348, 320), RESISTOR, 6)
        cv2.rectangle(frame, (332, 200), (364, 270), RESISTOR, -1)
        cv2.rectangle(frame, (332, 200), (364, 270), (40, 60, 80), 2)
        cv2.line(frame, (348, 320), (418, 320), RESISTOR, 6)

    # LED, drawn last so nothing covers it.
    if active(timeline.led_placed, t):
        lit = power_on and active(timeline.led_lit, t)
        cv2.line(frame, (418, 276), (418, 320), (210, 210, 210), 4)  # legs
        cv2.line(frame, (452, 276), (452, 352), (210, 210, 210), 4)
        if lit:
            overlay = frame.copy()
            cv2.circle(overlay, (435, 250), 62, LED_ON, -1)
            cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)
        cv2.circle(frame, (435, 250), 30, LED_ON if lit else LED_OFF, -1)
        cv2.circle(frame, (435, 250), 30, (245, 245, 245), 2)

    if active(timeline.ground_in, t):
        cv2.line(frame, (452, 352), (452, 404), WIRE_BLACK, 7)

    if power_on:
        cv2.rectangle(frame, (820, 220), (920, 300), BATTERY, -1)
        cv2.rectangle(frame, (820, 220), (920, 300), (200, 200, 200), 2)
        cv2.putText(frame, "9V", (838, 268), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEXT, 2)
        cv2.line(frame, (820, 240), (770, 141), WIRE_RED, 6)
    elif timeline.power_in is not None and t >= timeline.power_in:
        # Battery visible but disconnected during a correction.
        cv2.rectangle(frame, (820, 220), (920, 300), BATTERY, -1)
        cv2.rectangle(frame, (820, 220), (920, 300), (200, 200, 200), 2)
        cv2.putText(frame, "9V", (838, 268), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEXT, 2)

    # A hand occludes the board during the listed intervals.
    for start, end in timeline.occlude:
        if start <= t < end:
            cv2.ellipse(frame, (430, 250), (150, 90), 20, 0, 360, HAND, -1)
            cv2.putText(
                frame, "hand", (380, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, BG, 2
            )

    cv2.putText(
        frame, timeline.caption, (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, TEXT, 2
    )
    cv2.putText(
        frame,
        f"t={t:05.2f}s  SYNTHETIC FIXTURE",
        (40, 505),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (170, 180, 190),
        1,
    )
    return frame


def write_video(scenario_id: str, timeline: Timeline, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # VP8 in WebM: the one codec OpenCV can both write and read here, and that
    # every target browser can play back. An mp4v file would decode in OpenCV but
    # show nothing in Chrome, which would silently break evidence links.
    path = out_dir / f"{scenario_id}.webm"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"VP80"), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        raise SystemExit(
            "OpenCV could not open a VP8 WebM writer. Reinstall "
            "opencv-python-headless, which bundles the FFmpeg backend."
        )
    total = int(round(timeline.duration * FPS))
    for index in range(total):
        writer.write(draw_frame(timeline, index / FPS))
    writer.release()
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="generate one scenario id")
    parser.add_argument("--out", default=str(SAMPLES), help="output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    chosen = (
        {args.only: SCENARIOS[args.only]}
        if args.only
        else dict(SCENARIOS)
    )
    if args.only and args.only not in SCENARIOS:
        print(f"Unknown scenario {args.only}. Known: {', '.join(SCENARIOS)}")
        return 2

    registry: dict[str, dict] = {}
    for scenario_id, timeline in chosen.items():
        path = write_video(scenario_id, timeline, out_dir)
        registry[scenario_id] = {
            "file": path.name,
            "scenario": scenario_id,
            "sha256": sha256_file(path),
            "duration_s": timeline.duration,
            "kind": "expert" if scenario_id == "expert" else "attempt",
        }
        print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")

    index_path = out_dir / "scenarios.json"
    existing: dict = {"videos": {}}
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {"videos": {}}
    existing.setdefault("videos", {}).update(registry)
    existing["note"] = (
        "Synthetic fixtures generated by scripts/make_synthetic_video.py. The mock "
        "provider keys its scripted MOCK responses on these sha256 values."
    )
    index_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"wrote {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
