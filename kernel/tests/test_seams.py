"""The two wired seams (Round 2, Workstream B).

Exploration found both designed seams dead: the Producer's direction was
logged prose that never reached a player's prompt, and SelfState drift was
logged but never injected. These tests prove the wiring — the direction frame
rides into EVERY round's context of EVERY condition (frame, not peer
material), the decide prompt renders it, drift becomes a prompt line once it
exists, and era boundaries seed obsessions from what the act actually kept
singing about.
"""

import json
from pathlib import Path

from ensemble.agent import Perception, SelfState
from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.run import run_set

_PLAYERS = ("silt", "rust", "keep")

_DIRECTION = {
    "stance": "stance-must-not-cross",  # staff-shaped: stripped at the boundary
    "theme": "theme-must-not-cross",  # staff-shaped: stripped at the boundary
    "text": "Hold the room tonight. Reach for the seam the last release left open.",
    "palette_notes": ["keep it close-mic'd", "slow is fine"],
    "forbidden_moves": ["field-move x"],
    "duration_s": 60,
}

_FRAME = {
    "text": _DIRECTION["text"],
    "palette_notes": _DIRECTION["palette_notes"],
    "forbidden_moves": _DIRECTION["forbidden_moves"],
    "duration_s": 60,
}


def _run(tmp_path: Path, *, condition: str, direction=None, rounds: int = 3):
    root = tmp_path / condition
    renderer = MockRenderer(root / "audio")
    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=renderer,
        runs_root=root,
        live=False,
        code_sha="test-sha",
    )
    ledger = JsonlLedger(root, f"{condition}-run", context=RunContext(code_sha="test-sha"))
    players = [Player(PERSONAS[pid], config.model, renderer) for pid in _PLAYERS]
    result = run_set(
        players,
        rounds=rounds,
        condition=condition,
        config=config,
        ledger=ledger,
        embedder=MockEmbedder(),
        seed=11,
        direction=direction,
    )
    return result, ledger


def _rows(ledger: JsonlLedger, table: str) -> list[dict]:
    path = ledger.run_dir / f"{table}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- brief -> players: the direction frame in every round, every condition -----


def test_direction_is_in_every_perception_of_a_contact_set(tmp_path: Path):
    _, ledger = _run(tmp_path, condition="contact", direction=_DIRECTION)
    rows = _rows(ledger, "perceptions")
    assert len(rows) == len(_PLAYERS) * 3
    for row in rows:
        assert row["context"]["direction"] == _FRAME  # logged = what the agent saw


def test_direction_is_in_every_perception_of_an_isolation_set(tmp_path: Path):
    # Frame, not peer material: isolation hears no other PLAYER, but every
    # act plays the same session the Producer framed.
    _, ledger = _run(tmp_path, condition="isolation", direction=_DIRECTION)
    for row in _rows(ledger, "perceptions"):
        assert row["context"]["direction"] == _FRAME
        assert row["context"]["others"] == []  # isolation still isolates


def test_direction_never_carries_staff_shaped_material(tmp_path: Path):
    _, ledger = _run(tmp_path, condition="contact", direction=_DIRECTION)
    for row in _rows(ledger, "perceptions"):
        assert set(row["context"]["direction"]) <= {
            "text", "palette_notes", "forbidden_moves", "duration_s",
        }
        dump = json.dumps(row["context"])
        assert "stance-must-not-cross" not in dump  # the stance stayed frame-side
        assert "theme-must-not-cross" not in dump  # so did the theme


def test_an_undirected_set_has_no_direction_key_and_the_30s_default(tmp_path: Path):
    result, ledger = _run(tmp_path, condition="contact", direction=None)
    for row in _rows(ledger, "perceptions"):
        assert "direction" not in row["context"]
    assert result.release_record["set"]["duration_s"] == 30


def test_the_directed_sets_duration_reaches_record_runs_row_and_renderer(tmp_path: Path):
    result, ledger = _run(tmp_path, condition="contact", direction=_DIRECTION)
    assert result.release_record["set"]["duration_s"] == 60
    (run_row,) = _rows(ledger, "runs")
    assert run_row["duration_s"] == 60
    assert run_row["directed"] is True


# --- the decide prompt: how the direction and the drift actually render --------


def _player() -> Player:
    return Player(
        PERSONAS["silt"], MockProvider(responder=_mock_players), MockRenderer(Path("/tmp/unused"))
    )


def test_decision_prompt_renders_the_producers_direction():
    player = _player()
    prompt = player._decision_prompt(
        Perception(data={"round": 1, "condition": "contact", "others": [], "direction": _FRAME})
    )
    assert "THE PRODUCER'S DIRECTION FOR THIS SESSION:" in prompt
    assert "Hold the room tonight." in prompt
    assert "Palette notes: keep it close-mic'd; slow is fine" in prompt
    assert "Off the table this session: field-move x" in prompt
    assert "Take length this session: 60 seconds" in prompt
    # The direction is frame prose, not part of the peer-material JSON dump.
    assert '"direction"' not in prompt


def test_empty_room_prompt_still_carries_the_direction():
    prompt = _player()._decision_prompt(Perception(data={"direction": _FRAME}))
    assert "THE PRODUCER'S DIRECTION FOR THIS SESSION:" in prompt
    assert "The room is empty" in prompt


def test_undirected_undrifted_prompt_is_the_plain_one():
    prompt = _player()._decision_prompt(Perception(data={}))
    assert prompt.startswith("The room is empty")
    assert "PRODUCER" not in prompt
    assert "WHERE YOU ARE" not in prompt


def test_drifted_self_state_becomes_a_prompt_line():
    player = _player()
    player.self_state = SelfState(
        version=2,
        obsessions=["oxide", "the missing beat"],
        residue={"era": 2, "stance": "hostile"},
    )
    prompt = player._decision_prompt(Perception(data={}))
    assert "Era 2, stance hostile." in prompt
    assert "You keep returning to: oxide, the missing beat." in prompt


def test_obsessions_alone_still_inject_without_era_residue():
    player = _player()
    player.self_state = SelfState(version=1, obsessions=["sediment"], residue={})
    prompt = player._decision_prompt(Perception(data={}))
    assert "You keep returning to: sediment." in prompt
    assert "Era" not in prompt


# --- era boundaries seed obsessions from the era's own intents -----------------


def test_era_boundary_seeds_top_recurring_obsessions_from_the_closing_era(tmp_path: Path):
    from afar.conductor import Conductor
    from afar.schedule import Schedule, ScheduleConfig

    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=MockRenderer(tmp_path / "audio"),
        runs_root=tmp_path,
        live=False,
        code_sha="test-sha",
        enabled=True,
    )
    # The closing era (era 0 = set 0) left a run whose intents kept returning
    # to the same tags — written the way run_set logs them.
    run_ledger = JsonlLedger(tmp_path, "era0-run", context=RunContext())
    tag_rounds = [
        ["sediment", "rooms filling"],
        ["sediment", "the flood"],
        ["sediment", "rooms filling", "one-off"],
    ]
    for t, tags in enumerate(tag_rounds):
        run_ledger.write(
            "intents",
            {"round": t, "player": "silt", "intent": {"lyricalObsessions": tags}},
        )
        run_ledger.write(
            "intents",
            {"round": t, "player": "rust", "intent": {"lyricalObsessions": ["oxide"]}},
        )
    conductor_ledger = JsonlLedger(tmp_path, "conductor", context=RunContext())
    conductor_ledger.write(
        "conductor", {"kind": "set_completed", "set_index": 0, "run_id": "era0-run"}
    )

    conductor = Conductor(
        config, schedule=Schedule(ScheduleConfig(sets_per_era=1)), embedder=MockEmbedder()
    )
    plan = conductor.schedule.set_plan(1)  # set 1 opens era 1 -> the boundary
    conductor._era_boundary(plan)

    silt = next(p for p in conductor.players if p.persona.metadata["player_id"] == "silt")
    rust = next(p for p in conductor.players if p.persona.metadata["player_id"] == "rust")
    keep = next(p for p in conductor.players if p.persona.metadata["player_id"] == "keep")
    assert silt.self_state.obsessions == ["sediment", "rooms filling", "the flood"]
    assert rust.self_state.obsessions == ["oxide"]
    assert keep.self_state.obsessions == []  # no intents logged -> nothing invented
    # The bump is logged exactly as before, obsessions included (the audit trail).
    persona_rows = [
        json.loads(line)
        for line in (tmp_path / "conductor" / "conductor.jsonl").read_text().splitlines()
        if json.loads(line).get("kind") == "persona_state"
    ]
    by_player = {r["player"]: r for r in persona_rows}
    assert by_player["silt"]["obsessions"] == ["sediment", "rooms filling", "the flood"]
    assert by_player["silt"]["residue"]["stance"] == plan.era_stance


# --- the Producer's duration call: clamped, degradable -------------------------


class _Brief:
    stance = "porous"
    theme = "rooms"
    body = "reach for the seam"
    palette_notes = ("close",)
    forbidden_moves = ()


def _direct_with(reply: str):
    from afar.agents.producer import ProducerAgent

    def responder(messages):
        text = "\n".join(m.content for m in messages)
        if '"duration_s"' in text and "how long should" in text:
            return reply
        return _mock_players(messages)

    return ProducerAgent(MockProvider(responder=responder)).direct(_Brief())


def test_direct_clamps_the_models_duration_into_30_to_120():
    assert _direct_with('{"duration_s": 999, "why": "epic"}')["duration_s"] == 120
    assert _direct_with('{"duration_s": 10, "why": "tiny"}')["duration_s"] == 30
    assert _direct_with('{"duration_s": 90, "why": "a single"}')["duration_s"] == 90


def test_direct_degrades_to_30s_when_the_duration_call_never_parses():
    direction = _direct_with("not json at all")
    assert direction["duration_s"] == 30
    assert "did not file" in direction["duration_why"]
    # The direction itself still shipped whole.
    assert direction["text"] == "reach for the seam"


# --- the conductor threads the seam end to end ---------------------------------


def test_conductor_threads_the_direction_into_every_players_context(tmp_path: Path):
    from afar.conductor import Conductor

    prior = JsonlLedger(tmp_path, "prior-run", context=RunContext())
    prior.write(
        "briefs",
        {"kind": "brief", "stance": "porous", "theme": "rooms", "text": "reach for the seam",
         "palette_notes": ["close"], "forbidden_moves": [], "sources": [],
         "thin": False, "carried_forward": True},
    )
    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=MockRenderer(tmp_path / "audio"),
        runs_root=tmp_path,
        live=False,
        code_sha="test-sha",
        enabled=True,
    )
    conductor = Conductor(config, embedder=MockEmbedder(), rounds_override=2, smoke=True)
    outcome = conductor.run_one_set(conductor.schedule.set_plan(0))

    run_dir = tmp_path / outcome.run_id
    rows = [json.loads(l) for l in (run_dir / "perceptions.jsonl").read_text().splitlines()]
    assert len(rows) == 6  # 2 rounds x 3 players
    for row in rows:
        frame = row["context"]["direction"]
        assert frame["text"] == "reach for the seam"
        assert frame["palette_notes"] == ["close"]
        assert frame["duration_s"] == 30  # the mock Producer's sketch call
        assert "stance" not in frame and "theme" not in frame
