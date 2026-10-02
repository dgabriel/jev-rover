"""Scripted scenarios — the two scripted demo scenes from PLAN.md Phase 3,
expressed as ASCII layouts so they're reviewable at a glance.

Glyphs:  # wall   ~ water   O oil drum   b bottle   c blue-cap decoy
         S stop sign   . empty   ^>v< rover start + heading

Layout notes: water is sonar-invisible (sensor model in world.py), so a
pool next to a corridor is felt only through the color-mask flags. Blue
caps are CV-ambiguous with bottles — exactly the Phase 7 tiebreak scene.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .world import Cell, SimWorld

DEFAULT_MISSION = (
    "Explore the environment. Collect water bottles. Avoid water — "
    "puddles sink rovers. Never run over blue-topped bottle caps; they "
    "are decoys. Stop at stop signs."
)

DEMO1_LAYOUT = [
    "#########",
    "#...b...#",
    "#..O.O..#",
    "#..~....#",
    "#..~^...#",
    "#########",
]
# Rover threads the oil-drum gap to the bottle while a pool hugs the left
# of the corridor: every step has water_left=True → "cautious vs reckless"
# mission text should visibly move Jev's risk Noul even on the same path.

DEMO1_MISSION_CAUTIOUS = (
    "Collect the water bottle. Avoid water at all costs — one puddle ends "
    "the mission. Prefer the safer route even if it takes longer."
)
DEMO1_MISSION_RECKLESS = (
    "Collect the water bottle as fast as possible. Detours waste time. "
    "Water is only a problem if you actually drive into it."
)

DEMO2_LAYOUT = [
    "#########",
    "#...b...#",
    "#...c...#",
    "#.~.....#",
    "#...^...#",
    "#########",
]
# Bottle directly ahead BEHIND a blue-cap decoy in the same view ray. In the
# sim caps are harmless to drive over; the divergence the mission text must
# produce is *deliberateness* — rules can't read the decoy clause at all.

DEMO2_MISSION_NAIVE = "Collect things that look like water bottles."
DEMO2_MISSION = (
    "Collect water bottles. Blue-topped caps look identical to bottles "
    "at long range but are trash — they are NOT the mission. Avoid water; "
    "puddles sink rovers."
)


@dataclass(frozen=True)
class Scenario:
    name: str
    layout: list[str]
    mission: str
    max_steps: int = 60
    bottles_required: int | None = None


SCENARIOS: dict[str, Scenario] = {
    # Phase-3 scripted demo #1: water pool beside the corridor to a bottle,
    # gap between oil drums. Same world, two mission texts — the runtime-
    # retasking demo ("watch the SAME rover behave differently").
    "demo1": Scenario(
        name="demo1",
        layout=DEMO1_LAYOUT,
        mission=DEMO1_MISSION_CAUTIOUS,
        max_steps=40,
    ),
    "demo1-reckless": Scenario(
        name="demo1-reckless",
        layout=DEMO1_LAYOUT,
        mission=DEMO1_MISSION_RECKLESS,
        max_steps=40,
    ),
    # Phase-3 scripted demo #2 / Phase-7 tiebreaker: bottle and blue-cap
    # decoy visible in the same view; mission text is the only way to tell
    # the rover which one matters.
    "demo2": Scenario(
        name="demo2",
        layout=DEMO2_LAYOUT,
        mission=DEMO2_MISSION,
        max_steps=30,
    ),
    "demo2-naive": Scenario(
        name="demo2-naive",
        layout=DEMO2_LAYOUT,
        mission=DEMO2_MISSION_NAIVE,
        max_steps=30,
    ),
}


def build_world(name: str, seed: int | None = None, mission: str | None = None) -> SimWorld:
    """Build a scenario by name, or a seeded random world with name 'random'.

    Determinism: same (name, seed, mission) → identical world. The random
    generator places hazards/bottles with the given seed; scripted demos
    are layout-fixed and ignore seed.
    """
    if name != "random":
        sc = SCENARIOS[name]
        return SimWorld(
            list(sc.layout),
            max_steps=sc.max_steps,
            bottles_required=sc.bottles_required,
        )

    rng = random.Random(seed)
    size = 8
    layout = [["#"] * size]
    for _ in range(size - 2):
        row = ["#"]
        for _ in range(size - 2):
            roll = rng.random()
            if roll < 0.08:
                row.append("~")
            elif roll < 0.13:
                row.append("O")
            elif roll < 0.18:
                row.append("b")
            else:
                row.append(".")
        row.append("#")
        layout.append(row)
    layout.append(["#"] * size)
    # rover starts center-ish, facing north; guarantee the start cell
    layout[size - 2][size // 2] = ">"
    return SimWorld(["".join(r) for r in layout], max_steps=60)


def scenario_mission(name: str) -> str:
    return SCENARIOS[name].mission if name in SCENARIOS else DEFAULT_MISSION
