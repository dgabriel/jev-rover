"""The shared decision boundary: observation in, typed decision out.

Everything — simulator, physical rover thin client, rules baseline, mock,
real Jev client — speaks exactly these two shapes. That sameness is the
project's core architectural claim (see README).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

CELL_CM = 25  # one grid cell ≈ one floor-tile step on the physical mat

PERMITTED_ACTIONS = ("ADVANCE", "TURN_LEFT", "TURN_RIGHT", "RETREAT", "HALT")


@dataclass(frozen=True)
class Observation:
    """What the rover can know about the world right now.

    Field set = observation schema v2 from PLAN.md. The physical adapter
    fills it from sonar + camera; the simulator fills it from grid truth.
    """

    distance_ahead_cm: int
    stop_sign_visible: bool
    water_left: bool
    water_ahead: bool
    water_right: bool
    bottle_visible: bool
    bottle_ahead: bool
    path_left_blocked: bool
    path_ahead_blocked: bool
    path_right_blocked: bool
    bottles_collected: int = 0
    steps_taken: int = 0
    sunk: bool = False

    def to_state(self, mission: str) -> dict:
        """The `state` field of a systemone request (JSON keys per schema v2)."""
        return {
            "mission": mission,
            "observation": {
                "distanceAheadCm": self.distance_ahead_cm,
                "stopSignVisible": self.stop_sign_visible,
                "waterLeft": self.water_left,
                "waterAhead": self.water_ahead,
                "waterRight": self.water_right,
                "bottleVisible": self.bottle_visible,
                "bottleAhead": self.bottle_ahead,
                "pathLeftBlocked": self.path_left_blocked,
                "pathAheadBlocked": self.path_ahead_blocked,
                "pathRightBlocked": self.path_right_blocked,
                "bottlesCollected": self.bottles_collected,
                "stepsTaken": self.steps_taken,
            },
        }


@dataclass
class Decision:
    """One tick's answer, from any backend.

    `risk_p` is P(safe to proceed) from the risk Noul (or a backend's
    equivalent). `confidence` exists for Choice answers; None otherwise.
    """

    action: str
    probabilities: dict[str, float]
    confidence: float | None
    risk_p: float | None
    source: str  # "rules" | "mock" | the dated model pin from the API
    raw: dict = field(default_factory=dict)


def validate_decision(dec: Decision) -> list[str]:
    """Contract checks every backend must pass. Empty list = clean.

    NaN check matters: `0 <= nan <= 1` is False but `isinstance(nan, float)`
    is True, and a NaN probability silently poisons every downstream compare
    (this failure mode is documented in cosmic-oracle's client).
    """
    problems: list[str] = []
    if dec.action not in PERMITTED_ACTIONS:
        problems.append(f"action {dec.action!r} not in PERMITTED_ACTIONS")
    for opt, p in dec.probabilities.items():
        if opt not in PERMITTED_ACTIONS:
            problems.append(f"probability key {opt!r} not a permitted action")
        if not isinstance(p, (int, float)) or p != p or not (0 <= p <= 1):
            problems.append(f"probability for {opt!r} not finite in [0,1]: {p!r}")
    for name, v in (("confidence", dec.confidence), ("risk_p", dec.risk_p)):
        if v is not None and (not isinstance(v, (int, float)) or v != v or not (0 <= v <= 1)):
            problems.append(f"{name} not finite in [0,1]: {v!r}")
    return problems


def bar(prob: float, width: int = 20) -> str:
    """ASCII probability bar — the jev-gym-style UI primitive."""
    filled = round(max(0.0, min(1.0, prob)) * width)
    return "█" * filled + "·" * (width - filled)
