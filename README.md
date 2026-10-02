# Jev Rover

**Jev Rover** is a tiny autonomous rover experiment built around a simple question:

> What happens if we replace a hard-coded behavioral state machine with a constrained language-model decision layer?

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

Jev Rover instead converts physical sensor/camera input into a small semantic description of the world, combines that with a remotely configurable mission, and asks **Jev** to choose one action from a tightly constrained set.

## Architecture

```text
Camera / sensors
       ↓
   Perception
       ↓
Normalized observation
       ↓
Current mission ← Remote Mission Control
       ↓
      Jev
       ↓
Constrained decision
       ↓
 Safety envelope
       ↓
 Motor control
```

Jev itself is text-in/text-out. It does not directly process camera frames or control motors.

The perception layer converts camera input into structured information such as:

```json
{
  "stopSignVisible": false,
  "waterLeft": true,
  "waterAhead": false,
  "waterRight": false,
  "pathLeftBlocked": false,
  "pathAheadBlocked": true,
  "pathRightBlocked": false
}
```

Jev receives that observation plus the current mission and may choose only:

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
- Treat blue objects or regions as simple water candidates.
- Later, allow a vision system to recognize actual water rather than relying solely on color.

The stop sign is intentionally absurd in a Mars context.

## Why use Jev instead of a state machine?

The goal is **not** to use an LLM where a few `if` statements would work better.

Jev becomes useful when decisions involve:

- competing goals
- ambiguous perception
- uncertain observations
- previously unseen combinations of conditions
- semantic descriptions such as “possibly water” or “narrow but navigable”
- missions that change at runtime

For example:

```text
MISSION:
Investigate possible water, but prefer safer routes.

OBSERVATION:
Possible water detected to the right.
Right route is narrow.
Forward route is clear.
No stop sign detected.
```

A traditional state machine requires an explicit rule for that combination.

Jev can reason from the mission and observation and select one of the permitted actions.

The design principle is:

> **Use deterministic code for perception plumbing, motor control, and safety. Use Jev for judgment under ambiguity.**

## Remote Mission Control

The Raspberry Pi will expose a tiny local web interface, likely reachable as something similar to:

```text
http://jev-rover.local
```

From a phone or laptop, an operator can change the rover mission while it is running.

For example, the mission could change from:

```text
Search for possible water.
Investigate blue objects.
Avoid collisions.
Continue exploring otherwise.
```

to:

```text
Explore cautiously.
Ignore weak water candidates.
Prefer large open spaces.
Halt when encountering unfamiliar objects.
```

The rover should change behavior on its next decision cycle without changing or redeploying code.

This runtime retasking is one of the central demonstrations of Jev Rover.

## Safety

Jev does **not** receive unrestricted motor control.

Hard-coded safety logic sits between Jev and the motors.

Examples:

- prohibit forward movement when an obstacle is extremely close
- enforce short movement durations
- automatically halt if the decision loop fails
- restrict Jev to the five permitted commands

So Jev controls **behavioral intent**, while deterministic software controls what the hardware is physically allowed to do.

## Development Plan

Development starts entirely in simulation.

The simulator provides synthetic perception and allows testing different missions, obstacles, stop signs, blue objects, and water candidates.

Once behavior is useful in simulation, the same normalized observation and decision interfaces will be connected to:

- Raspberry Pi
- camera
- simple computer vision
- motor driver
- two-wheel differential-drive chassis

The intent is to keep the physical rover extremely small and inexpensive.

## Repository

`dgabriel/jev-rover`

Planned structure:

```text
jev-rover/
├── simulator/
├── src/
│   ├── perception
│   ├── decision
│   ├── mission
│   └── safety
├── mission-control/
├── rover/
├── tests/
└── README.md
```

The most important architectural requirement is that the **simulator and physical rover use the same Jev decision interface**.read
