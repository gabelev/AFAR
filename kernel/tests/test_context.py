"""THE manipulation, tested: build_context is the only place condition branches.

If contact leaks round-t material, or isolation leaks any other-player
material at all, every downstream influence number is meaningless — so these
tests are about what the context must NOT contain as much as what it must.
"""

import json
from pathlib import Path

import pytest

from afar.log import JsonlLedger, RunContext
from afar.perception.context import RoundEntry, RunView, build_context

_PLAYERS = ("silt", "rust", "keep")


def _view(rounds: int = 2) -> RunView:
    """A history where every entry names its (player, round) in every field."""
    view = RunView()
    for t in range(rounds):
        view.append_round(
            {
                pid: RoundEntry(
                    player_id=pid,
                    line=f"{pid} line r{t}",
                    intent={"seedPrompt": f"{pid} dna r{t}"},
                    content_hash=f"hash-{pid}-{t}",
                )
                for pid in _PLAYERS
            }
        )
    return view


def test_contact_context_contains_the_others_previous_round():
    context = build_context("silt", 2, _view(), "contact")
    others = {entry["player_id"]: entry for entry in context["others"]}
    assert set(others) == {"rust", "keep"}
    for pid, entry in others.items():
        assert entry["line"] == f"{pid} line r1"
        assert entry["intent"] == {"seedPrompt": f"{pid} dna r1"}
        assert entry["content_hash"] == f"hash-{pid}-1"
    assert context["own"] == {
        "player_id": "silt",
        "line": "silt line r1",
        "intent": {"seedPrompt": "silt dna r1"},
        "content_hash": "hash-silt-1",
    }


def test_contact_uses_round_t_minus_1_never_round_t():
    # The view already holds round-1 entries; a context for round 1 must only
    # reach round 0 — round-t material must be invisible even when it exists.
    context = build_context("silt", 1, _view(rounds=2), "contact")
    dump = json.dumps(context)
    assert "r0" in dump
    assert "r1" not in dump


@pytest.mark.parametrize("condition", ["isolation", "solo", "parallel"])
def test_alone_conditions_contain_no_other_player_material(condition):
    context = build_context("silt", 2, _view(), condition)
    assert context["others"] == []
    dump = json.dumps(context)
    assert "rust" not in dump
    assert "keep" not in dump
    # Own history still flows: three solo artists, not three amnesiacs.
    assert context["own"]["line"] == "silt line r1"


def test_round_zero_has_no_own_and_empty_others():
    for condition in ("contact", "isolation", "parallel"):
        context = build_context("silt", 0, RunView(), condition)
        assert "own" not in context
        assert context["others"] == []


def test_context_is_json_serializable_and_survives_the_ledger_verbatim(tmp_path: Path):
    context = build_context("silt", 2, _view(), "contact")
    assert json.loads(json.dumps(context)) == context
    ledger = JsonlLedger(tmp_path, "ctx-run", context=RunContext(code_sha="x"))
    ledger.write("perceptions", {"player": "silt", "context": context})
    (line,) = (ledger.run_dir / "perceptions.jsonl").read_text().splitlines()
    assert json.loads(line)["context"] == context


def test_unknown_condition_refuses_rather_than_guessing():
    with pytest.raises(ValueError, match="condition"):
        build_context("silt", 0, RunView(), "chaos")
