"""Episode runner: observe → decide → (envelope) → act → trace.

Every tick is logged to logs/sim-runs.jsonl — when the OpenRouter backend
is live these traces are the Phase 8 τ-calibration dataset's sibling
(failure traces feed the confidence-threshold judgment too).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from jevrover.decision.types import Decision, Observation, PERMITTED_ACTIONS, bar, validate_decision
from jevrover.safety import apply_envelope
from jevrover.simulator.world import SimWorld


def run_episode(
    world: SimWorld,
    decider,
    mission: str,
    render: bool = True,
    trace_path: str | Path = "logs/sim-runs.jsonl",
    risk_floor: float = 0.35,
) -> dict:
    trace = Path(trace_path)
    trace.parent.mkdir(parents=True, exist_ok=True)

    vetoes = 0
    decisions = {a: 0 for a in PERMITTED_ACTIONS}
    events: list[str] = []
    seen: dict[tuple, int] = {}

    if render:
        print(f"scenario | {decider.name} | mission: {mission[:72]}\n")

    while not world.done:
        # Stateless policies (rules, Jev, any observe→decide function) can
        # loop: same observation → same answer → same observation. Detect it,
        # name it, end the episode — a loop is a result, not a hang.
        sig = world.signature()
        seen[sig] = seen.get(sig, 0) + 1
        if seen[sig] >= 4:
            world.done_reason = "looping"
            break

        obs = world.observe()
        dec = decider.decide(obs, mission)
        problems = validate_decision(dec)
        if problems:
            raise RuntimeError(f"decision broke contract from {decider.name}: {problems}")

        action, vetoed = apply_envelope(obs, dec, risk_floor)
        vetoes += int(vetoed)
        decisions[action] += 1
        outcome = world.step(action)
        if outcome.event:
            events.append(outcome.event)

        _record(trace, obs, dec, action, vetoed, outcome.event, world, mission)
        if render:
            print(world.render())
            print(_frame(obs, dec, action, vetoed, outcome.event, decider.name))
            print()

    summary = {
        "decider": decider.name,
        "status": world.done_reason or "unknown",
        "steps": world.steps,
        "collected": world.bottles_collected,
        "vetoes": vetoes,
        "actions": decisions,
        "events": events,
    }
    if render:
        print(f"--- {summary['status']} in {world.steps} steps, "
              f"bottles {world.bottles_collected}, vetoes {vetoes} ---")
    return summary


def _frame(obs: Observation, dec: Decision, action: str, vetoed: bool, event: str | None, name: str) -> str:
    lines = [f"[{name}] step {obs.steps_taken + 1}"]
    for opt in sorted(dec.probabilities, key=dec.probabilities.get, reverse=True):
        mark = "  ⇒" if opt == dec.action else ""
        lines.append(f"  {opt:<10} {bar(dec.probabilities[opt])} {dec.probabilities[opt]:.2f}{mark}")
    conf = "—" if dec.confidence is None else f"{dec.confidence:.2f}"
    risk = "—" if dec.risk_p is None else f"{dec.risk_p:.2f}"
    lines.append(f"  conf {conf}  safe-to-proceed {risk}")
    if vetoed:
        lines.append(f"  ENVELOPE VETO → {action}")
    if event:
        lines.append(f"  *** {event} ***")
    return "\n".join(lines)


def _record(trace: Path, obs, dec, action, vetoed, event, world, mission) -> None:
    trace.open("a").write(json.dumps({
        "ts": time.time(),
        "observation": obs.to_state(mission)["observation"],
        "decision": {
            "source": dec.source,
            "action": dec.action,
            "probabilities": dec.probabilities,
            "confidence": dec.confidence,
            "risk_p": dec.risk_p,
        },
        "envelope": {"action": action, "vetoed": vetoed},
        "event": event,
        "world": {"steps": world.steps, "sunk": world.sunk,
                  "collected": world.bottles_collected,
                  "done": world.done_reason},
    }) + "\n")
