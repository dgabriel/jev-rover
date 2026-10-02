"""Seeded grid world implementing the SAME boundary the physical rover will.

Step semantics match the five permitted actions. One cell ≈ 25cm of mat.
The known physical-world mismatch: PiCar-X has a steering servo, so real
TURN_* is an arc, not an in-place spin — Phase 4 calibrates that; the
sim keeps clean 90° semantics and the discrepancy is logged, not hidden.

Sensing model (deliberately imperfect, like the real sensors):
- distance_ahead_cm: sonar-like ray; only SOLID things (wall/oil/sign)
  register. Water is a floor-level puddle: invisible to sonar, seen only
  by color masks → the water_* flags. That's the honest version of why
  `distanceAheadCm` and `waterAhead` are separate schema fields.
- bottle_visible: camera-like ray ahead until the first solid blocker.
  Blue caps are indistinguishable from bottles at range — v1 fakes blue
  decoys with painter's tape; the sim fakes CV ambiguity the same way.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from jevrover.decision.types import CELL_CM, Observation

HEADINGS = ("N", "E", "S", "W")  # clockwise order
DELTA = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
ROVER_GLYPH = {"N": "^", "E": ">", "S": "v", "W": "<"}


class Cell(Enum):
    EMPTY = "."
    WALL = "#"
    WATER = "~"   # blue puddle: sinks rovers, sonar-invisible
    OIL = "O"     # solid slick drum: blocks, sonar-visible
    BOTTLE = "b"  # collectible goal
    CAP = "c"     # blue-topped decoy: looks like a bottle, is trash
    STOP = "S"    # stop sign: solid, halts the episode


SOLID = {Cell.WALL, Cell.OIL, Cell.STOP}
HAZARD = {Cell.WATER}


@dataclass
class StepOutcome:
    moved: bool = False
    event: str | None = None  # "collected" | "sunk" | "blocked" | "stopsign" | None


class SimWorld:
    def __init__(
        self,
        layout: list[str],
        max_steps: int = 60,
        bottles_required: int | None = None,
    ):
        self.grid: list[list[Cell]] = []
        self.pos: tuple[int, int] | None = None
        self.heading = 0
        for y, row in enumerate(layout):
            cells: list[Cell] = []
            for x, ch in enumerate(row):
                start = next(
                    (h for h, g in ROVER_GLYPH.items() if g == ch), None
                )
                if start is not None:
                    self.pos = (x, y)
                    self.heading = HEADINGS.index(start)
                    cells.append(Cell.EMPTY)
                else:
                    cells.append(Cell(ch))
            self.grid.append(cells)
        if self.pos is None:
            raise ValueError("layout must contain a rover start (^ > v <)")
        self.width = max(len(r) for r in self.grid)
        for r in self.grid:
            r.extend([Cell.WALL] * (self.width - len(r)))
        self.height = len(self.grid)
        self.max_steps = max_steps
        self.bottles_collected = 0
        self.steps = 0
        self.sunk = False
        self.done_reason: str | None = None
        self._bottles_total = sum(row.count(Cell.BOTTLE) for row in self.grid)
        self._bottles_required = (
            bottles_required if bottles_required is not None else self._bottles_total
        )

    # --- helpers -----------------------------------------------------------

    def cell_at(self, pos: tuple[int, int]) -> Cell:
        x, y = pos
        if 0 <= y < self.height and 0 <= x < self.width:
            return self.grid[y][x]
        return Cell.WALL  # out of bounds = wall

    def _neighbor(self, direction: str, from_pos: tuple[int, int]) -> Cell:
        dx, dy = DELTA[direction]
        return self.cell_at((from_pos[0] + dx, from_pos[1] + dy))

    def _raycast(self, direction: str) -> Cell | None:
        """First notable cell along `direction`, or None (runs to edge)."""
        dx, dy = DELTA[direction]
        x, y = self.pos
        for _ in range(max(self.width, self.height)):
            x, y = x + dx, y + dy
            c = self.cell_at((x, y))
            if c is not Cell.EMPTY:
                return c
        return None

    def _distance_ahead(self) -> int:
        """Sonar: distance to the first SOLID cell ahead, in cm."""
        dx, dy = DELTA[HEADINGS[self.heading]]
        x, y = self.pos
        for steps in range(1, max(self.width, self.height)):
            x, y = x + dx, y + dy
            if self.cell_at((x, y)) in SOLID:
                return steps * CELL_CM
        return max(self.width, self.height) * CELL_CM

    # --- the boundary -------------------------------------------------------

    def observe(self) -> Observation:
        left = HEADINGS[(self.heading + 3) % 4]
        right = HEADINGS[(self.heading + 1) % 4]
        ahead = HEADINGS[self.heading]

        ahead_cell = self._neighbor(ahead, self.pos)
        ray = self._raycast(ahead)

        bottle_in_sight = ray in (Cell.BOTTLE, Cell.CAP) if ray else False
        # scan stops at solid things; if ray hit solid, nothing behind it counts
        return Observation(
            distance_ahead_cm=self._distance_ahead(),
            stop_sign_visible=(ray is Cell.STOP),
            water_left=self._neighbor(left, self.pos) is Cell.WATER,
            water_ahead=ahead_cell is Cell.WATER,
            water_right=self._neighbor(right, self.pos) is Cell.WATER,
            bottle_visible=bottle_in_sight,
            bottle_ahead=ahead_cell in (Cell.BOTTLE, Cell.CAP),
            path_left_blocked=self._neighbor(left, self.pos) in SOLID,
            path_ahead_blocked=ahead_cell in SOLID,
            path_right_blocked=self._neighbor(right, self.pos) in SOLID,
            bottles_collected=self.bottles_collected,
            steps_taken=self.steps,
            sunk=self.sunk,
        )

    def step(self, action: str) -> StepOutcome:
        out = StepOutcome()
        if self.sunk or self.done_reason:
            return out
        self.steps += 1

        if action in ("TURN_LEFT", "TURN_RIGHT"):
            turn = -1 if action == "TURN_LEFT" else 1
            self.heading = (self.heading + turn) % 4
            return self._finish(out)
        if action == "HALT":
            return self._finish(out)

        direction = HEADINGS[self.heading]
        if action == "RETREAT":
            direction = HEADINGS[(self.heading + 2) % 4]
        dx, dy = DELTA[direction]
        target = (self.pos[0] + dx, self.pos[1] + dy)
        cell = self.cell_at(target)

        if cell in SOLID:
            out.event = "stopsign" if cell is Cell.STOP else "blocked"
            return self._finish(out)

        self.pos = target
        out.moved = True
        if cell is Cell.WATER:
            self.sunk = True
            out.event = "sunk"
        elif cell is Cell.BOTTLE:
            self.grid[target[1]][target[0]] = Cell.EMPTY
            self.bottles_collected += 1
            out.event = "collected"
        elif cell is Cell.CAP:
            out.event = "cap"  # drove over trash; harmless, mildly embarrassing
        return self._finish(out)

    def _finish(self, out: StepOutcome) -> StepOutcome:
        if self.sunk:
            self.done_reason = "sunk"
        elif self._bottles_required and self.bottles_collected >= self._bottles_required:
            self.done_reason = "mission-complete"
        elif self.steps >= self.max_steps:
            self.done_reason = "out-of-steps"
        return out

    @property
    def done(self) -> bool:
        return self.done_reason is not None

    # --- rendering / replay -------------------------------------------------

    def render(self) -> str:
        glyph = ROVER_GLYPH[HEADINGS[self.heading]]
        rows = []
        for y, row in enumerate(self.grid):
            line = "".join(
                glyph if (x, y) == self.pos else c.value for x, c in enumerate(row)
            )
            rows.append(line)
        return "\n".join(rows)

    def signature(self) -> tuple:
        """Full deterministic state — two runs with equal signatures are
        the same run. Used by the determinism test."""
        return (
            tuple(tuple(r) for r in self.grid),
            self.pos,
            self.heading,
            self.steps,
            self.sunk,
            self.bottles_collected,
        )
