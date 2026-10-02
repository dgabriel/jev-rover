"""The honest baseline: a dozen `if` statements.

This is the thing Jev must beat. Per the plan's intellectual honesty, the
rules will usually WIN on scripted scenes — the demos measure that instead
of hiding it. Note what the baseline cannot do: parse mission text. The
mission clause lives in `mission_text` purely so traces show what it was
told; these rules would behave identically under any mission. Jev doesn't.
"""
from __future__ import annotations

from .types import Decision, Observation, PERMITTED_ACTIONS


def _dist(choice: str) -> dict[str, float]:
    base = {a: 0.025 for a in PERMITTED_ACTIONS}
    base[choice] = 0.9
    return base


class RulesDecider:
    name = "rules"

    def decide(self, obs: Observation, mission: str) -> Decision:
        # Hard truths first, in priority order. This is a state machine.
        if obs.stop_sign_visible:
            choice = "HALT"
        elif obs.bottle_ahead:
            choice = "ADVANCE"
        elif obs.water_ahead or obs.path_ahead_blocked:
            if not obs.water_left and not obs.path_left_blocked:
                choice = "TURN_LEFT"
            elif not obs.water_right and not obs.path_right_blocked:
                choice = "TURN_RIGHT"
            else:
                choice = "RETREAT"
        elif obs.bottle_visible or not obs.path_ahead_blocked:
            choice = "ADVANCE"
        else:
            choice = "TURN_LEFT"

        # Risk honesty: adjacent water is *risky-ish*, water ahead is death.
        # A flat 0.0 for any-adjacent water gets envelope-paralyzed (it can
        # veto the turn-out too if the gate ever blocks in-place actions).
        if obs.water_ahead:
            risk = 0.05
        elif obs.water_left or obs.water_right:
            risk = 0.5
        else:
            risk = 0.98

        return Decision(
            action=choice,
            probabilities=_dist(choice),
            # Fixed, uninformative confidence: the rules never know when they're
            # wrong. That asymmetry is half the Phase 8 payload.
            confidence=0.95,
            risk_p=risk,
            source="rules",
            raw={"rule": "hardcoded-priority-list"},
        )
