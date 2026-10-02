"""Sim correctness + the determinism guarantee Phase 1 is done-when."""
from jevrover.simulator import build_world
from jevrover.decision.rules import RulesDecider
from jevrover.simulator.runner import run_episode


def test_seeded_random_worlds_replay_identically():
    a = build_world("random", seed=7)
    b = build_world("random", seed=7)
    assert a.signature() == b.signature()


def test_scripted_scenario_layout_is_fixed():
    a = build_world("demo1")
    b = build_world("demo1")
    assert a.signature() == b.signature()


def test_rules_episode_replays_identically(tmp_path):
    w1, w2 = build_world("demo1"), build_world("demo1")
    d = RulesDecider()
    run_episode(w1, d, "m", render=False, trace_path=tmp_path / "a.jsonl")
    run_episode(w2, RulesDecider(), "m", render=False, trace_path=tmp_path / "b.jsonl")
    assert w1.signature() == w2.signature()


def test_water_sinks():
    w = build_world("random", seed=1)
    # place water directly ahead manually and drive into it
    x, y = w.pos
    dxdy = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    from jevrover.simulator.world import HEADINGS, Cell
    dx, dy = dxdy[HEADINGS[w.heading]]
    w.grid[y + dy][x + dx] = Cell.WATER
    out = w.step("ADVANCE")
    assert out.event == "sunk" and w.sunk and w.done


def test_bottle_is_collected():
    w = build_world("demo1")
    from jevrover.simulator.world import HEADINGS, Cell
    x, y = w.pos
    dx, dy = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}[HEADINGS[w.heading]]
    w.grid[y + dy][x + dx] = Cell.BOTTLE
    out = w.step("ADVANCE")
    assert out.event == "collected" and w.bottles_collected == 1


def test_turn_rotates_heading():
    w = build_world("demo1")
    before = w.heading
    w.step("TURN_LEFT")
    assert w.heading == (before + 3) % 4
    w.step("TURN_RIGHT")
    assert w.heading == before
