#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Phase 0 acceptance test: one pinned Jev call over the OpenRouter route.

Sends a v0 rover observation + mission with the project's real batched
decision contract — action Choice over the five permitted actions plus a
risk Noul, in ONE systemone request — then validates the response shape,
prints the answer distribution, and appends the raw call to
logs/jev-calls.jsonl (Phase 8's τ-calibration data starts accumulating
from literally the first call).

Reference: ../cosmic-oracle/docs/jev-openrouter.md (verified 2026-09-26).

Usage:
    export OPENROUTER_API_KEY=...   # same key as cosmic-oracle's Worker
    uv run scripts/jev_smoke.py
    uv run scripts/jev_smoke.py --no-send   # just print the request body
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import json, os, sys, time
from pathlib import Path

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jevrover.decision.openrouter import ENDPOINT, MODEL, build_questions
from jevrover.decision.types import PERMITTED_ACTIONS

LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "jev-calls.jsonl"

# The scripted demo tie-breaker scene: water on the right, a bottle ahead,
# the left path blocked. A hand-rolled rules table has no principled answer
# to this; we want Jev's full distribution, not just the argmax.
STATE = {
    "mission": (
        "Collect water bottles. Avoid water — puddles sink rovers. "
        "Never run over blue-topped bottle caps; they are decoys."
    ),
    "observation": {
        "distanceAheadCm": 30,
        "stopSignVisible": False,
        "waterLeft": False,
        "waterAhead": False,
        "waterRight": True,
        "bottleVisible": True,
        "bottleAhead": True,
        "pathLeftBlocked": True,
        "pathAheadBlocked": False,
        "pathRightBlocked": False,
    },
}

PERMITTED_ACTIONS = list(PERMITTED_ACTIONS)  # tuple in types.py; local list for set-membership msgs

QUESTIONS = build_questions()


def bar(prob: float, width: int = 24) -> str:
    filled = round(prob * width)
    return "█" * filled + "·" * (width - filled)


def log_call(record: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")


def send(api_key: str, body: dict) -> dict:
    """POST with retry on transient errors only (per cosmic-oracle notes)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    transient = {429, 500, 502, 503, 524, 529}
    for attempt in range(4):
        if attempt:
            time.sleep(2**attempt)
        try:
            resp = httpx.post(ENDPOINT, headers=headers, json=body, timeout=30)
        except httpx.HTTPError as e:
            print(f"transport error: {e}", file=sys.stderr)
            continue
        if resp.status_code == 401:
            sys.exit("401 — key rejected. Export the same OpenRouter key the Worker uses.")
        if resp.status_code == 402:
            sys.exit("402 — insufficient OpenRouter credits. Top up, or this is the demo fallback story.")
        if resp.status_code in transient:
            print(f"{resp.status_code} from upstream, retrying…", file=sys.stderr)
            continue
        if resp.status_code != 200:
            sys.exit(f"{resp.status_code}: {resp.text[:400]}")
        return resp.json()
    sys.exit("upstream kept failing after retries")


def validate(body: dict, data: dict) -> list[str]:
    """Return a list of shape problems; empty list = contract holds."""
    problems = []
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return ["no `answers` map in response"]

    action = answers.get("action", {})
    if action.get("type") != "choice":
        problems.append("action answer is not a choice")
    else:
        if action.get("choice") not in PERMITTED_ACTIONS:
            problems.append(f"choice {action.get('choice')!r} not in permitted set")
        for opt, p in (action.get("probabilities") or {}).items():
            if not isinstance(p, (int, float)) or not (0 <= p <= 1):
                problems.append(f"probability for {opt!r} out of [0,1]: {p!r}")

    noul = answers.get("safe_to_proceed", {})
    if noul.get("type") != "noul":
        problems.append("safe_to_proceed answer is not a noul")
    else:
        v = noul.get("noul")
        # cosmic-oracle lesson: `isinstance(v, (int,float))` admits NaN,
        # which would silently compare False everywhere downstream.
        if not isinstance(v, (int, float)) or v != v or not (0 <= v <= 1):
            problems.append(f"noul value not a finite probability: {v!r}")

    pin = data.get("model", "")
    if not str(pin).startswith(MODEL):
        problems.append(f"model pin drifted: asked {MODEL}, got {pin!r}")

    return problems


def main() -> None:
    body = {"model": MODEL, "state": STATE, "questions": QUESTIONS}
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    if "--no-send" in sys.argv or not api_key:
        print("Request body that WOULD be sent:\n")
        print(json.dumps(body, indent=2))
        if not api_key:
            print("\nSet OPENROUTER_API_KEY (same key as cosmic-oracle's Worker), then rerun.", file=sys.stderr)
            sys.exit(1)
        return

    data = send(api_key, body)
    log_call({"ts": time.time(), "request": body, "response": data})

    problems = validate(body, data)

    answers = data["answers"]
    action, noul = answers["action"], answers["safe_to_proceed"]
    probs = action.get("probabilities", {})

    print(f"model (pin):   {data.get('model')}")
    print(f"provider:      {data.get('provider')}")
    print("\naction distribution:")
    for opt in sorted(probs, key=probs.get, reverse=True):
        mark = "  ← chosen" if opt == action.get("choice") else ""
        print(f"  {opt:<10} {bar(probs[opt])} {probs[opt]:.2f}{mark}")
    print(f"\naction confidence: {action.get('confidence')}")
    print(f"safe_to_proceed:   {bar(noul['noul'])} {noul['noul']:.2f}")

    usage = data.get("usage", {})
    print(
        f"\ntokens: {usage.get('input_tokens')} in / {usage.get('output_tokens')} out"
        f"   cost: ${usage.get('cost', 0):.6f}"
    )
    print(f"raw call logged → {LOG_FILE.relative_to(LOG_FILE.parent.parent)}")

    if problems:
        print("\nSHAPE PROBLEMS:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(2)
    print("\ncontract holds. Phase 0 access step: done.")


if __name__ == "__main__":
    main()
