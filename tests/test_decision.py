"""Decision-boundary contract tests + the safety envelope's hard vetoes."""
import pytest

from jevrover.decision.mock_jev import MockJevDecider
from jevrover.decision.openrouter import build_questions
from jevrover.decision.rules import RulesDecider
from jevrover.decision.types import (
    PERMITTED_ACTIONS,
    Decision,
    Observation,
    validate_decision,
)
from jevrover.safety import apply_envelope


def obs(**kw):
    base = dict(
        distance_ahead_cm=75, stop_sign_visible=False,
        water_left=False, water_ahead=False, water_right=False,
        bottle_visible=False, bottle_ahead=False,
        path_left_blocked=False, path_ahead_blocked=False, path_right_blocked=False,
    )
    base.update(kw)
    return Observation(**base)


@pytest.mark.parametrize("cls", [RulesDecider, MockJevDecider])
def test_deciders_satisfy_contract(cls):
    d = cls()
    dec = d.decide(obs(), "collect bottles, avoid water")
    assert validate_decision(dec) == []
    assert dec.action in PERMITTED_ACTIONS


def test_envelope_vetoes_advance_into_wall():
    dec = Decision("ADVANCE", {"ADVANCE": 1.0}, 0.9, 0.9, "test")
    action, vetoed = apply_envelope(obs(path_ahead_blocked=True), dec)
    assert action == "HALT" and vetoed


def test_envelope_vetoes_advance_into_water():
    dec = Decision("ADVANCE", {"ADVANCE": 1.0}, 0.9, 0.9, "test")
    action, vetoed = apply_envelope(obs(water_ahead=True), dec)
    assert action == "HALT" and vetoed


def test_envelope_halts_on_low_risk_noul():
    dec = Decision("ADVANCE", {"ADVANCE": 1.0}, 0.9, 0.10, "test")
    action, vetoed = apply_envelope(obs(), dec)
    assert action == "HALT" and vetoed


def test_envelope_passes_clean_decision():
    dec = Decision("ADVANCE", {"ADVANCE": 1.0}, 0.9, 0.98, "test")
    action, vetoed = apply_envelope(obs(), dec)
    assert action == "ADVANCE" and not vetoed


def test_rules_ignores_mission_text():
    # The baseline's documented limitation: its behavior is invariant to the
    # mission — the thing Jev is actually for. This test guards the claim.
    d = RulesDecider()
    a = d.decide(obs(bottle_ahead=True), "collect bottles")
    b = d.decide(obs(bottle_ahead=True), "ignore all bottles")
    assert a.action == b.action


def test_questions_contract_matches_smoke_test():
    q = build_questions()
    assert q["action"]["type"] == "choice"
    assert set(q["action"]["criteria"]) == set(PERMITTED_ACTIONS)
    assert q["safe_to_proceed"]["type"] == "noul"


def test_openrouter_decider_refuses_without_key(monkeypatch):
    from jevrover.decision.openrouter import OpenRouterDecider
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterDecider()
