"""Offline stand-in for Jev: same output shape, no network, deterministic.

Not a toy: it mimics the failure modes the plan documents — non-determinism
across calls for the SAME state (seeded here for replayability), and
occasional low-confidence wobble that the safety gate must catch. Use it
for all dev loops; spend API money only when behavior is worth measuring.
"""
from __future__ import annotations

import hashlib

from .rules import RulesDecider
from .types import Decision, Observation, PERMITTED_ACTIONS


class MockJevDecider:
    name = "mock"

    def __init__(self, seed: int = 0, wobble_rate: float = 0.15):
        self.rules = RulesDecider()
        self.seed = seed
        self.wobble_rate = wobble_rate

    def _rng(self, obs: Observation, salt: str) -> float:
        """Deterministic per (seed, state, salt) → reproducible 'drift'."""
        h = hashlib.sha256(f"{self.seed}|{salt}|{obs}".encode()).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF

    def decide(self, obs: Observation, mission: str) -> Decision:
        base = self.rules.decide(obs, mission)
        roll = self._rng(obs, "wobble")

        if roll < self.wobble_rate:
            # The wobble: mock pick something plausible-but-wrong, WITH the
            # tell the real model gives — confidence drops. The gate exists
            # for exactly this tick.
            alt = next(a for a in ("TURN_LEFT", "HALT", "RETREAT", "TURN_RIGHT")
                       if a != base.action)
            probs = {a: 0.05 for a in PERMITTED_ACTIONS}
            probs[alt] = 0.5 + 0.1 * self._rng(obs, "altconf")
            probs[base.action] = 1.0 - probs[alt] - 0.05 * 3
            confidence = 0.35 + 0.2 * self._rng(obs, "conf")
            action = alt
        else:
            probs = dict(base.probabilities)
            # Jev-style softness: smear the peak a little.
            peak = probs[base.action]
            spread = 0.05 + 0.1 * self._rng(obs, "spread")
            probs[base.action] = max(0.0, peak - spread)
            others = [a for a in PERMITTED_ACTIONS if a != base.action]
            for a in others:
                probs[a] += spread / len(others)
            confidence = 0.75 + 0.2 * self._rng(obs, "conf")
            action = base.action

        if obs.water_ahead:
            risk = 0.1
        elif obs.water_left or obs.water_right:
            risk = 0.5
        else:
            risk = 0.98
        risk -= 0.1 * self._rng(obs, "risknoise")
        return Decision(
            action=action,
            probabilities=probs,
            confidence=round(confidence, 3),
            risk_p=round(max(0.0, min(1.0, risk)), 3),
            source="mock",
            raw={"mocked": True, "wobbled": roll < self.wobble_rate},
        )
