# Recording footage KIFACH can actually read

The system can only assess what a camera plainly shows. These rules are what
separates a demo that works from one that returns "inconclusive" for everything.

## Camera

- **Fixed viewpoint.** Phone on a small tripod or propped against a book, looking
  straight down at the work surface. Do not move it between the expert
  demonstration and the learner attempts.
- **Fill the frame with the work.** The whole task should occupy most of the
  frame. If a checkpoint is a 5 mm gap on a breadboard, it needs to be visible at
  a glance in a still frame.
- **1080p at 30 fps is plenty.** KIFACH samples 2 frames per second and resizes
  the long side to 768 px.

## Lighting and background

- Even, indirect light. Avoid a single hard lamp: its shadows move with your
  hands and read as changes.
- Matte, contrasting background — a sheet of plain paper or card under the work.
- No glare on shiny parts. If the LED or a metal tool flares, tilt the light.

## The task itself

- **One action at a time.** Complete an action, then pause for about a second
  with your hands out of the frame. That pause is what makes a checkpoint
  visible; without it, every frame shows a hand.
- **Large, distinct components.** Big resistor, thick jumper wires in clearly
  different colours, a chunky battery pack.
- **Keep it short.** 20–40 seconds. Longer footage costs provider calls without
  adding evidence.
- **Do not narrate with your hands.** Gestures over the work look like actions.

## What to record for a complete demo

| Clip | What to do | What it should prove |
| --- | --- | --- |
| `expert` | The task done correctly, in the recommended order | The procedure KIFACH derives and the expert publishes |
| `correct` | The same task, done correctly by the learner | VERIFIED |
| `alternate_order` | Independent steps swapped (ground before resistor) | VERIFIED — the engine allows any valid order |
| `wrong_order` | Power applied while the resistor row is **clearly visible and empty** | NOT VERIFIED, with supported evidence |
| `uncertain` | The checkpoint hidden by a hand for most of the clip | INCONCLUSIVE, not a failure |
| `corrected` | Wrong order, then power removed, resistor added, power reapplied | VERIFIED with a resolved alert |

The wrong-order clip is the one people get wrong. For KIFACH to say a step was
*skipped* rather than *not seen*, the camera must show the place the step belongs
and show that nothing is there. If your hand covers that row, the honest answer
is "inconclusive", and that is what you will get.

## Naming and registering clips

The offline mock provider answers only for footage it can identify. Name a file
after its scenario (`wrong_order.webm`) or pass the scenario explicitly when
uploading. Real providers have no such restriction — they observe whatever you
give them.

## Synthetic fixtures

`python scripts/make_synthetic_video.py` writes the six clips above as drawn
WebM animations. They are deterministic, they exercise every path, and they are
what the automated tests use — but they are drawings. Perception quality can only
be judged against real recordings.
