#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Run the simulator against any decision backend.

    uv run scripts/run_sim.py --scenario demo1                 # rules baseline
    uv run scripts/run_sim.py --scenario demo2 --decider mock --seed 7
    uv run scripts/run_sim.py --scenario demo1 --compare       # rules vs mock
    uv run scripts/run_sim.py --scenario demo1 --decider openrouter --live
    uv run scripts/run_sim.py --scenario demo1 --mission "Be reckless."

`--live` is required with the openrouter backend so nobody spends API
money by accident. Without it you get the honest rules baseline for free.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jevrover.decision.mock_jev import MockJevDecider
from jevrover.decision.rules import RulesDecider
from jevrover.simulator import build_world, scenario_mission
from jevrover.simulator.runner import run_episode


def make_decider(name: str, seed: int, live: bool):
    if name == "rules":
        return RulesDecider()
    if name == "mock":
        return MockJevDecider(seed=seed)
    if name == "openrouter":
        if not live:
            sys.exit("refusing to spend: pass --live with --decider openrouter")
        from jevrover.decision.openrouter import OpenRouterDecider
        return OpenRouterDecider()
    raise ValueError(name)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="demo1",
                   choices=["demo1", "demo1-reckless", "demo2", "demo2-naive", "random"])
    p.add_argument("--decider", default="rules", choices=["rules", "mock", "openrouter"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--mission", default=None, help="override the scenario's mission text")
    p.add_argument("--compare", action="store_true",
                   help="run rules vs mock on the same world side by side")
    p.add_argument("--live", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    mission = args.mission or scenario_mission(args.scenario)

    backends = ["rules", "mock"] if args.compare else [args.decider]
    summaries = []
    for name in backends:
        world = build_world(args.scenario, seed=args.seed)
        decider = make_decider(name, args.seed, args.live)
        s = run_episode(world, decider, mission, render=not args.quiet)
        s["backend"] = name
        summaries.append(s)

    if args.compare:
        print("\n=== side by side (same world, same mission) ===")
        for s in summaries:
            print(f"  {s['backend']:<6} {s['status']:<16} steps {s['steps']:>3}  "
                  f"collected {s['collected']}  vetoes {s['vetoes']}")
    elif args.quiet:
        s = summaries[0]
        print(f"{s['status']} in {s['steps']} steps — collected {s['collected']}, vetoes {s['vetoes']}")


if __name__ == "__main__":
    main()
