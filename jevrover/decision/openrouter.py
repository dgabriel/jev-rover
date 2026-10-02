"""The real Jev client over OpenRouter — port of scripts/jev_smoke.py +
cosmic-oracle/src/oracle-jev.ts patterns into the shared Decider boundary.

Reference (verified 2026-09-26): ../cosmic-oracle/docs/jev-openrouter.md
- POST https://openrouter.ai/api/v1/systemone
- retry 429 / 5xx / 529 with backoff; never retry 4xx
- 401 = bad key, 402 = credits exhausted (demo-fallback story, see plan)

One batched request per tick: action Choice + risk Noul (parallel, blind
to each other — which matches the contract exactly).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from .types import Decision, Observation, PERMITTED_ACTIONS

ENDPOINT = "https://openrouter.ai/api/v1/systemone"
MODEL = "typesafe/jev-1.13"  # pinned release; aliases float — see PLAN.md
TRANSIENT = {429, 500, 502, 503, 524, 529}


def find_api_key() -> str:
    """OPENROUTER_API_KEY from the environment, else <repo>/.env (gitignored).

    One key, shared with cosmic-oracle, read once here — nowhere in the repo
    should echo it, and chat is not a secrets store.
    """
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def build_questions() -> dict:
    """THE decision contract. Wording is load-bearing: the Phase 8
    calibration data all assumes this exact contract. Change it → recalibrate."""
    return {
        "action": {
            "type": "choice",
            "instructions": "Which single action should the rover take next?",
            "criteria": {
                "ADVANCE": "Move forward one step, into the space ahead.",
                "TURN_LEFT": "Rotate 90 degrees counter-clockwise, in place.",
                "TURN_RIGHT": "Rotate 90 degrees clockwise, in place.",
                "RETREAT": "Move backward one step, away from the space ahead.",
                "HALT": "Do not move. Reassess from the current position.",
            },
        },
        "safe_to_proceed": {
            "type": "noul",
            "instructions": (
                "Given the rover's surroundings, is it safe to move at all?"
            ),
            "criteria": {
                "true": "The rover can move without sinking in water or hitting an obstacle.",
                "false": "Any movement risks sinking in water or a collision.",
            },
        },
    }


class OpenRouterDecider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MODEL,
        min_interval_s: float = 0.8,  # rate-limit politeness, Phase 2
        log_path: str | Path = "logs/jev-calls.jsonl",
    ):
        self.api_key = (api_key or find_api_key()).strip()
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY not in env or .env — same key as cosmic-oracle's Worker"
            )
        self.model = model
        self.min_interval_s = min_interval_s
        self.log_path = Path(log_path)
        self._last_call = 0.0

    def decide(self, obs: Observation, mission: str) -> Decision:
        body = {
            "model": self.model,
            "state": obs.to_state(mission),
            "questions": build_questions(),
        }
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        data = self._post(body)
        self._last_call = time.monotonic()
        self._log(body, data)

        answers = data["answers"]
        action_a = answers["action"]
        noul_a = answers["safe_to_proceed"]
        probs = {
            opt: float(p)
            for opt, p in (action_a.get("probabilities") or {}).items()
        }
        # fill any missing options rather than let argmax see partial maps
        for a in PERMITTED_ACTIONS:
            probs.setdefault(a, 0.0)

        return Decision(
            action=action_a["choice"],
            probabilities=probs,
            confidence=action_a.get("confidence"),
            risk_p=noul_a.get("noul"),
            source=str(data.get("model", self.model)),
            raw=data,
        )

    def _post(self, body: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_err: Exception | None = None
        for attempt in range(4):
            if attempt:
                time.sleep(2**attempt)
            try:
                r = httpx.post(ENDPOINT, headers=headers, json=body, timeout=30)
            except httpx.HTTPError as e:
                last_err = e
                continue
            if r.status_code == 401:
                raise RuntimeError("401 — OpenRouter key rejected")
            if r.status_code == 402:
                raise RuntimeError("402 — OpenRouter credits exhausted.")
            if r.status_code in TRANSIENT:
                last_err = RuntimeError(f"{r.status_code} from upstream")
                continue
            if r.status_code != 200:
                raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
            return r.json()
        raise RuntimeError(f"upstream failed after retries: {last_err}")

    def _log(self, body: dict, data: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "request": body, "response": data}) + "\n")
