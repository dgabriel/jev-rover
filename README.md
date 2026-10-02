# Jev Rover

**Jev Rover** is a tiny autonomous rover experiment built around a simple
question:

> What happens if we replace a hard-coded behavioral state machine with a
> typed, probabilistic decision model?

The rover follows the classic robotics loop:

**sense → decide → act**

The difference is in the **decide** step.

A conventional beginner robot might contain logic such as:

```text
if obstacle ahead:
    turn left
else:
    move forward
```

Jev Rover instead converts physical sensor/camera input into a small
semantic description of the world, combines that with a remotely
configurable mission, and asks **Jev** — TypeSafe AI's "System One" typed
decision model ([docs](https://docs.typesafe.ai),
[community wiki](https://jevwiki.ai)) — to choose one action from a
tightly constrained set.

Jev never generates text. It answers **typed questions** — Choices,
Scores, Nouls — returning an answer plus per-option probabilities and a
confidence score, typically in tens of milliseconds, for fractions of a
penny. Think of it less as a brain and more as a set of very fast,
English-steerable reflexes.

## Architecture

```text
Camera / sensors
       ↓
   Perception  (color masks · YOLO · ultrasonic · QR*)
       ↓
Normalized observation
       ↓
Current mission ← Remote Mission Control
       ↓
      Jev  ──confidence──→ low? → generative LLM escalation
       ↓                        → narration tier (Jev can't speak)
Typed decision (action + probabilities + confidence)
       ↓
 Safety envelope
       ↓
 Motor control
```

\* strictly dessert, see PLAN.md.

A single decision cycle is one batched `systemone` request:

- **state**: the observation below + the current mission text
- **questions**: an `action` **Choice** over five options whose criteria
  come from the mission, and a `risk` **Noul** ("is the rover one move
  from collision?")

Calls go to the **OpenRouter** System One endpoint, model pinned to
`typesafe/jev-1.13` (the dated build in each response is logged — the
Phase-8 confidence calibration depends on pinned weights, not floats).
The API key is shared with this project's sibling,
[cosmic-jev](https://github.com/dgabriel/cosmic-jev) (checked out locally
as `cosmic-oracle`) — its `docs/jev-openrouter.md` is the
verified request/response reference, and its client and Worker are the
reference implementations being ported to Python. TypeSafe's direct
console key remains a documented fallback.

Jev is text-in/typed-out. It does not process camera frames, does not
control motors, and cannot be talked into emitting prose — because it
structurally has none.

The perception layer converts camera/sensor input into structured
information such as:

```json
{
  "distanceAheadCm": 30,
  "stopSignVisible": false,
  "waterLeft": true,
  "waterAhead": false,
  "waterRight": false,
  "bottleVisible": true,
  "bottleAhead": true,
  "pathLeftBlocked": false,
  "pathAheadBlocked": true,
  "pathRightBlocked": false
}
```

Jev's action Choice may select only:

```text
ADVANCE
TURN_LEFT
TURN_RIGHT
RETREAT
HALT
```

## Initial Mission

The Mars-rover-inspired default mission is:

- Explore the environment.
- Avoid obstacles.
- Stop when a stop sign is visible.
- Investigate possible evidence of water.
- Treat blue objects or regions as simple water candidates, and anything
  that looks like a bottle (COCO literally has a "bottle" class) as a
  water *container* candidate.

The stop sign is intentionally absurd in a Mars context.

## Why use Jev instead of a state machine?

Honest answer for this rover's daily life: **a dozen `if` statements
would usually win.** Fixed missions over a small observation space are
very rule-able, and this project measures that instead of denying it
(see the head-to-head in PLAN.md).

Two things survive scrutiny:

1. **The policy becomes runtime-editable English.** A state machine's
   mission is compiled into rules. Here the mission is the *criteria
   text of the decision question* — a stranger can rewrite it from a
   phone while the rover drives, including missions nobody anticipated at
   build time. No redeploy, no rules engine.
2. **Judgment under ambiguity with a calibrated escape hatch.**

```text
MISSION:
Investigate possible water, but prefer safer routes.

OBSERVATION:
Possible water to the right. Right route narrow. Forward clear.
```

Jev returns a probability distribution over the five actions — you can
*watch it hesitate*. And when confidence drops below a tuned threshold,
control escalates to a generative LLM that answers the same Choice. Fast
reflexes where they suffice, expensive reasoning only where needed —
published as the REFLEX architecture
([arXiv 2609.26532](https://arxiv.org/abs/2609.26532)), whose honest
limits ("the hard decision is usually *whether* to act, and cheap tiers
win when routing is easy") we take as design constraints.

The design principle:

> **Deterministic code owns perception plumbing, motor control, and
> safety. Jev owns fast typed judgment. Generative models own rare
> escalation and all narration.**

## Remote Mission Control

The brain runs on a laptop; the rover is a thin client. A tiny local web
interface (something like `http://jev-rover.local`) edits the mission
live. The mission becomes the question criteria, so the rover's behavior
changes on its next decision cycle without touching code. This runtime
retasking is one of the central demonstrations of Jev Rover.

## Safety

- Jev's output is a five-way Choice; nothing else reaches the motors.
- Deterministic safety logic sits between decisions and motors on **both**
  sides of the wifi: the brain vetoes actions that contradict hard
  observation facts, and the rover itself enforces bounded timed bursts,
  an ultrasonic floor check, and a dead-man's switch that halts the robot
  if the brain goes silent.
- Jev is never the sole safety control — this is also the vendor's own
  guidance.

## Development Plan

Development starts entirely in simulation, against the same decision
interface the physical rover will use. Once behavior is useful in
simulation, the brain is pointed at the hardware unchanged:

- SunFounder **PiCar-X** as the platform — chassis, drive, 18650s +
  charger, pan/tilt 5MP camera, ultrasonic, and a speaker + mic in one
  $90 box — with a Raspberry Pi 5 **1GB** (~$45; the thin client idles
  under ~400MB, and everything RAM-hungry — YOLO, LLM escalation, TTS —
  stays on the laptop) running `/sense`, `/frame`, `/act`
- Kit camera + trivial CV (HSV color masks; pretrained YOLO for bottles)
- Ultrasonic on the pan/tilt head for obstacle truth

The physical rover stays extremely small, inexpensive (~$145 all-in),
and one-box-procured.
**Full phased plan, shopping list, and fallback ladders: [PLAN.md](PLAN.md).**

## Quickstart

**Status:** Phase 1 mostly built — the simulator, the shared decision
boundary (rules baseline / mock / OpenRouter backends), and the safety
envelope all exist and pass tests. Remaining before hardware: the live
Jev measurement pass (needs `OPENROUTER_API_KEY`).

```bash
export OPENROUTER_API_KEY=...     # same key as cosmic-oracle's Worker
uv run scripts/jev_smoke.py       # Phase 0: fire one pinned call, ~$0.00002

uv run scripts/run_sim.py --scenario demo1                 # rules baseline
uv run scripts/run_sim.py --scenario demo2 --compare       # rules vs mock, same world
uv run scripts/run_sim.py --scenario demo1 --decider openrouter --live  # real Jev
uv run --extra dev pytest          # contract + determinism tests
```

Scenarios `demo1`/`demo1-reckless` and `demo2`/`demo2-naive` are the same
worlds with different mission texts — the runtime-retasking demo in
miniature. Every raw call lands in `logs/jev-calls.jsonl` and every tick
in `logs/sim-runs.jsonl` — those two files are the τ-calibration dataset
for the Phase 8 confidence cascade.

## Repository

`dgabriel/jev-rover`

```text
jev-rover/
├── jevrover/
│   ├── decision/      # ✓ types.py (Observation/Decision boundary),
│   │                  #   rules.py (honest baseline), mock_jev.py,
│   │                  #   openrouter.py (real client, single batched call)
│   ├── simulator/     # ✓ world.py (seeded grid + honest sensor model),
│   │                  #   scenarios.py (scripted demo scenes), runner.py
│   └── safety.py      # ✓ deterministic veto envelope (brain side)
├── scripts/
│   ├── jev_smoke.py   # ✓ Phase 0 acceptance test for the Jev route
│   └── run_sim.py     # ✓ episode CLI: --scenario/--decider/--compare
├── rover/             # Phase 4-5: Pi thin client (/sense, /frame, /act)
├── mission-control/   # Phase 6: live mission editor
├── logs/              # runtime-only; gitignored. jev-calls + sim traces
├── tests/             # ✓ contract, determinism, envelope vetoes
├── PLAN.md
└── README.md
```

The most important architectural requirement is that the **simulator and
physical rover use the same decision interface** — `Observation` in,
`Decision` out, from every backend.

## References & prior art

- [TypeSafe AI docs](https://docs.typesafe.ai) · [jevwiki.ai](https://jevwiki.ai) —
  what Jev is, and how (not) to build with it
- [REFLEX: Efficient Selective Control in LLM Agents](https://arxiv.org/abs/2609.26532) —
  the confidence-gated cascade, with honest negative results
- [jev-gym](https://pyshine.com/Jev-Gym-A-System-One-Decision-Agent-Controls-Any-Gymnasium-Env/) —
  one typed decision contract across 8 Gymnasium environments, and the
  probability-bar UI we're imitating
- [Made with Jev: dual-arm robot](https://madewithjev.com/builds/dual-arm-robot) —
  decisions to Jev, IK and physics to code

"Jev drives a robot" is a genre, not a first. This one is small, honest,
and in a room with you.
