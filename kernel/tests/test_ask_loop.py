"""THE ACCEPTANCE for artist agency: the conductor knocks, the artist decides.

Everything offline (MockProvider + MockRenderer + MockEmbedder, publish forced
dry). What this file is for:

- the LOOP is a tick, not a booking: a record happens only after a yes, and a
  tick where everyone declines is a healthy, cheap, logged turn of the piece;
- a NO is respected — it costs no audio-minutes, earns a cooldown, and the
  reason is in the log verbatim;
- the COOLDOWNS are read back out of the log, so a fresh process asks exactly
  who the last one would have;
- nothing in the ask path can carry a staff voice, even when the log rows it
  reads from are stuffed with one;
- the BUDGET still governs: on a spent day nobody is even asked.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from ensemble.providers.model import Message, MockProvider

from afar.asking import Urge, ask_states
from afar.config import AfarConfig, _mock_players
from afar.conductor import Conductor, hours_since, next_tick_index
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _config(root: Path, *, minutes: float = 110.0, model=None, **kw) -> AfarConfig:
    return AfarConfig(
        model=model or MockProvider(responder=_mock_players),
        renderer=MockRenderer(root / "audio"),
        runs_root=root,
        live=False,
        code_sha="test-sha",
        enabled=True,
        album_tracks=2,
        track_seconds=30,
        daily_audio_minutes=minutes,
        **kw,
    )


def _conductor(root: Path, *, clock=lambda: NOW, **kw) -> Conductor:
    return Conductor(_config(root, **kw), embedder=MockEmbedder(), clock=clock)


def _stop_after_one_pass(conductor: Conductor) -> None:
    """Let the loop take exactly one turn: the first sleep ends the run."""

    def fake_idle(seconds: float, kind: str, **row) -> None:
        conductor._stop = True

    conductor._idle = fake_idle  # type: ignore[method-assign]


def _rows(root: Path) -> list[dict]:
    path = root / "conductor" / "conductor.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _answers(**by_artist: bool):
    """A model that answers the ask however the test says, and writes real
    albums through the normal mock for everything else."""

    def responder(messages):
        user = messages[-1].content if messages else ""
        if "HOURS SINCE YOUR LAST RECORD:" in user and '"ready"' in user:
            system = messages[0].content
            for artist_id, ready in by_artist.items():
                if artist_id.upper() in system or artist_id in system:
                    return json.dumps(
                        {"ready": ready, "why": f"{artist_id} says {'yes' if ready else 'no'}"}
                    )
            return json.dumps({"ready": False, "why": "nothing here today"})
        return _mock_players(messages)

    return MockProvider(responder=responder)


# --- the tick -----------------------------------------------------------------


def test_a_yes_makes_a_record_and_the_reason_is_logged_with_it(tmp_path: Path):
    conductor = _conductor(tmp_path)
    plan = conductor.schedule.set_plan(0)
    answered = conductor.ask_round(0, plan.seed)
    assert answered is not None
    artist_id, urge = answered
    assert urge.ready and urge.why

    size = conductor.affordable(conductor.budget.remaining_minutes)
    outcome = conductor.run_one_album(conductor.plan_record(artist_id, 0, size))
    assert outcome.completed and outcome.artist_id == artist_id

    kinds = [r["kind"] for r in _rows(tmp_path)]
    assert kinds.index("tick") < kinds.index("artist_asked") < kinds.index("album_booked")
    asked = next(r for r in _rows(tmp_path) if r["kind"] == "artist_asked")
    assert asked["artist"] == artist_id and asked["ready"] is True and asked["why"]


def test_a_tick_where_everyone_declines_costs_nothing_and_says_who_and_why(tmp_path: Path):
    """The crux: no is a real answer. It must be free — no audio-minutes, no
    record, no failure — and it must leave the reason behind."""
    conductor = _conductor(tmp_path, model=_answers())  # everybody says no
    _stop_after_one_pass(conductor)
    assert conductor.run_forever() == 0

    rows = _rows(tmp_path)
    assert conductor.budget.spent_minutes == 0.0
    assert not any(r["kind"] in ("album_booked", "album_failed") for r in rows)
    declines = [r for r in rows if r["kind"] == "artist_asked"]
    assert declines and all(r["ready"] is False and r["why"] for r in declines)
    assert any(r["kind"] == "nobody_recorded" for r in rows)


def test_the_conductor_stops_knocking_at_the_first_yes(tmp_path: Path):
    """One record per tick: the budget, the renderer and the publish path are
    all one at a time, so a yes ends the round."""
    conductor = _conductor(tmp_path, model=_answers(), asks_per_tick=5)
    yes_for = conductor.roster[3]
    conductor.config.model = _answers(**{yes_for: True})
    conductor.config.ask_model = conductor.config.model
    answered = conductor.ask_round(0, 0)
    assert answered is not None and answered[0] == yes_for
    asked = [r["artist"] for r in _rows(tmp_path) if r["kind"] == "artist_asked"]
    assert asked[-1] == yes_for
    assert len(asked) <= 5


def test_only_eligible_artists_are_asked_and_at_most_the_tick_allowance(tmp_path: Path):
    conductor = _conductor(tmp_path, model=_answers(), asks_per_tick=2)
    conductor.ask_round(0, 0)
    conductor.ask_round(1, 0)
    rows = _rows(tmp_path)
    ticks = [r for r in rows if r["kind"] == "tick"]
    assert all(len(t["asking"]) <= 2 for t in ticks)
    # Nobody who declined in tick 0 is knocked on again in tick 1 — the
    # cooldown came from the log, not from anything held in memory.
    assert not set(ticks[0]["asking"]) & set(ticks[1]["asking"])


def test_a_fresh_process_asks_who_the_last_one_would_have(tmp_path: Path):
    """The conductor remembers nothing: cooldowns are re-derived on boot."""
    first = _conductor(tmp_path, model=_answers(), asks_per_tick=2)
    first.ask_round(0, 0)
    declined = {r["artist"] for r in _rows(tmp_path) if r["kind"] == "artist_asked"}

    again = _conductor(tmp_path, model=_answers(), asks_per_tick=2)
    states = ask_states(_rows(tmp_path), again.roster)
    assert all(states[a].declines == 1 for a in declined)
    again.ask_round(again.tick_index, 0)
    fresh = [r for r in _rows(tmp_path) if r["kind"] == "tick"][-1]["asking"]
    assert not set(fresh) & declined


def test_the_tick_cursor_resumes_from_the_log(tmp_path: Path):
    assert next_tick_index([]) == 0
    assert next_tick_index([{"kind": "tick", "tick": 0}, {"kind": "tick", "tick": 1}]) == 2
    conductor = _conductor(tmp_path, model=_answers())
    conductor.ask_round(conductor.tick_index, 0)
    assert _conductor(tmp_path, model=_answers()).tick_index == 1


def test_a_silent_model_is_not_an_answer_and_earns_no_cooldown(tmp_path: Path):
    """An ask that fails is a machine failure, not an artist's decision — it
    must never be logged as a decline, or a flaky provider would silence the
    town."""
    conductor = _conductor(tmp_path, model=MockProvider(responder=lambda m: "not json"))
    conductor.config.ask_model = conductor.config.model
    assert conductor.ask_round(0, 0) is None
    rows = _rows(tmp_path)
    assert not any(r["kind"] == "artist_asked" for r in rows)
    assert [r["kind"] for r in rows].count("ask_failed") >= 1
    states = ask_states(rows, conductor.roster)
    assert all(s.declines == 0 for s in states.values())


# --- the money ----------------------------------------------------------------


def test_a_spent_day_asks_nobody(tmp_path: Path):
    """A yes the conductor could not honour would be a lie."""
    conductor = _conductor(tmp_path, minutes=0.5)
    _stop_after_one_pass(conductor)
    assert conductor.run_forever() == 0
    rows = _rows(tmp_path)
    assert any(r["kind"] == "cap_reached" for r in rows)
    assert not any(r["kind"] in ("tick", "artist_asked") for r in rows)


# --- the law ------------------------------------------------------------------


def test_the_ask_prompt_carries_the_sleeve_and_never_a_staff_word(tmp_path: Path):
    """End to end, through a real logged record with the staff's whole
    apparatus bolted onto it: what reaches the artist at the ASK is sleeve
    text and its own clock, and nothing the staff ever wrote."""
    conductor = _conductor(tmp_path)
    size = conductor.affordable(110.0)
    maker = conductor.roster[0]
    conductor.run_one_album(conductor.plan_record(maker, 0, size))

    # Bolt the staff onto the logged album row, exactly as a republished,
    # reacted-to record carries them.
    run_dir = next(p for p in tmp_path.iterdir() if p.name.endswith(maker))
    path = run_dir / "albums.jsonl"
    row = json.loads(path.read_text().splitlines()[0])
    row["record"]["staff"] = {
        "critic": {"review": "SECRETCRITIC"},
        "producer": {"direction": "SECRETDIRECTION"},
        "muse": {"brief": "SECRETBRIEF"},
        "listener": {"reaction": "SECRETREACTION"},
        "archivist": {"liner_notes": "SECRETLINER"},
    }
    row["record"]["album"]["rationale"] = "SECRETRATIONALE"
    path.write_text(json.dumps(row) + "\n")

    seen: list[str] = []
    conductor.config.ask_model = MockProvider(
        responder=lambda messages: (
            seen.append("\n".join(m.content for m in messages))
            or json.dumps({"ready": False, "why": "listening"})
        )
    )
    listener = conductor.roster[1]
    conductor.ask(listener)

    prompt = seen[0]
    for marker in (
        "SECRETCRITIC",
        "SECRETDIRECTION",
        "SECRETBRIEF",
        "SECRETREACTION",
        "SECRETLINER",
        "SECRETRATIONALE",
    ):
        assert marker not in prompt
    # The sleeve did come through, and so did the artist's own clock.
    assert row["record"]["album"]["title"] in prompt
    assert "HOURS SINCE YOUR LAST RECORD:" in prompt


def test_the_ask_is_a_question_not_an_instruction(tmp_path: Path):
    """If the prompt ever stops saying that no is a legitimate answer, this
    change has quietly become rotation with extra steps."""
    conductor = _conductor(tmp_path)
    seen: list[str] = []
    conductor.config.ask_model = MockProvider(
        responder=lambda messages: (
            seen.append(messages[-1].content)
            or json.dumps({"ready": False, "why": "nothing yet"})
        )
    )
    urge = conductor.ask(conductor.roster[0])
    prompt = seen[0].lower()
    assert "nobody has booked you" in prompt
    assert "saying no costs you nothing" in prompt
    assert "both answers are real" in prompt
    assert urge.ready is False


def test_the_persona_prompt_is_the_system_message_verbatim(tmp_path: Path):
    conductor = _conductor(tmp_path)
    artist_id = conductor.roster[0]
    seen: list[Message] = []
    conductor.config.ask_model = MockProvider(
        responder=lambda messages: (
            seen.extend(messages) or json.dumps({"ready": False, "why": "no"})
        )
    )
    conductor.ask(artist_id)
    assert seen[0].role == "system"
    assert seen[0].content == conductor.artist(artist_id).persona.base_prompt


# --- the clock ----------------------------------------------------------------


def test_hours_since_reads_the_log_and_is_honest_about_never():
    assert hours_since("", NOW) is None
    assert hours_since("not a date", NOW) is None
    assert hours_since((NOW - timedelta(hours=30)).isoformat(), NOW) == pytest.approx(30.0)
    # A clock that ran backwards reads as "just now", never as the future.
    assert hours_since((NOW + timedelta(hours=5)).isoformat(), NOW) == 0.0
