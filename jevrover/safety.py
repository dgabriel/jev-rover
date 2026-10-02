"""The deterministic safety envelope — code, not vibes, between every
decision and the wheels. Runs on BOTH sides of the wifi eventually;
this is the brain-side copy (the rover-side one lives in Phase 4/5,
enforcing bursts, floor checks, and the dead-man's switch).

Veto rules, all derived from hard observation facts:
  1. never move into a blocked cell
  2. never move into water (puddles sink rovers — mission fact, not
     model opinion)
  3. if the risk Noul says the world is unsafe, HALT until it isn't
The physical-rover wrinkle lives in PLAN.md: TURN_* is an arc, not a
spin, so "never into a blocked cell" becomes a calibration problem in
Phase 4. Here, semantics are clean.
"""
from __future__ import annotations

from jevrover.decision.types import Decision, Observation

RISK_FLOOR = 0.35  # provisional; Phase 8 calibrates from our own logs


def apply_envelope(obs: Observation, dec: Decision, risk_floor: float = RISK_FLOOR) -> tuple[str, bool]:
    """Return (final_action, vetoed?)."""
    if obs.sunk:
        return "HALT", dec.action != "HALT"

    # hard facts first — they outrank any probability mass
    if dec.action == "ADVANCE" and (
        obs.path_ahead_blocked or obs.water_ahead or obs.stop_sign_visible
    ):
        return "HALT", True

    # risk-gate: vetoes MOVES only. In-place turns must stay legal even when
    # the world feels unsafe — blocking them paralyzed the rover beside every
    # water edge (observed livelock: 13 vetoes, 0 progress, demo2 walkthrough).
    if (
        dec.action in ("ADVANCE", "RETREAT")
        and dec.risk_p is not None
        and dec.risk_p < risk_floor
    ):
        return "HALT", True

    return dec.action, False
