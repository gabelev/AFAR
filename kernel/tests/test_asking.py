"""The ask, in the pure half: the answer's shape and the cooldown's curve.

`afar.asking` is where "artists decide when they record" stops being a
sentiment and becomes arithmetic anyone can check. Two claims are tested here:
a model's answer is parsed generously but is never allowed to be reasonless,
and the cooldown that follows a "no" is bounded at both ends — long enough
that declining means something, capped so declining can never become exile.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from afar.asking import (
    DEFAULT_ASK_COOLDOWN_HOURS,
    DEFAULT_ASK_COOLDOWN_MAX_HOURS,
    DEFAULT_RECORD_COOLDOWN_HOURS,
    AskState,
    Urge,
    ask_order,
    ask_states,
    askable,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
ROSTER = ("silt", "rust", "keep", "vess", "lolgorithm")


def _ts(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


# --- the answer ---------------------------------------------------------------


def test_a_plain_yes_and_a_plain_no_both_parse():
    yes = Urge.from_json('{"ready": true, "why": "the record is already there"}', artist_id="silt")
    assert (yes.ready, yes.artist_id) == (True, "silt")
    no = Urge.from_json('{"ready": false, "why": "I put one out on Tuesday"}', artist_id="rust")
    assert no.ready is False and no.why == "I put one out on Tuesday"


@pytest.mark.parametrize(
    "raw,ready",
    [
        ('```json\n{"ready": "yes", "why": "it is there"}\n```', True),
        ('Here you go:\n{"ready": "no", "why": "nothing yet"}', False),
        ('{"ready": "TRUE", "why": "a whole record"}', True),
        ('{"ready": 0, "why": "not this week"}', False),
    ],
)
def test_the_shapes_a_cheap_model_actually_emits_all_parse(raw, ready):
    assert Urge.from_json(raw, artist_id="silt").ready is ready


def test_an_answer_with_no_reason_is_refused():
    """The distribution of who declines and why is the observable this whole
    change exists to produce — an answer that will not say why is worth
    re-asking for (the retry ladder does exactly that)."""
    with pytest.raises(ValueError):
        Urge.from_json('{"ready": false}', artist_id="silt")
    with pytest.raises(ValueError):
        Urge.from_json('{"ready": true, "why": "   "}', artist_id="silt")


def test_an_unusable_reply_raises_rather_than_guessing():
    for raw in ("", "no idea", '{"why": "something"}', '{"ready": "maybe", "why": "hm"}'):
        with pytest.raises(ValueError):
            Urge.from_json(raw, artist_id="silt")


# --- the curve ----------------------------------------------------------------


def test_the_cooldown_doubles_with_consecutive_declines_and_stops_at_a_week():
    hours = [
        AskState("silt", last_event="declined", declines=n).cooldown_hours()
        for n in range(1, 8)
    ]
    assert hours[:4] == [12.0, 24.0, 48.0, 96.0]
    assert hours[4:] == [DEFAULT_ASK_COOLDOWN_MAX_HOURS] * 3
    # The cap is the point: a month of declining still gets you asked weekly.
    assert max(hours) == DEFAULT_ASK_COOLDOWN_MAX_HOURS == 168.0


def test_declining_can_never_become_exile():
    """Whatever an artist has said, and however often, it is asked again
    inside a week. Nobody is ever silenced by arithmetic."""
    forever = AskState("silt", last_event="declined", declines=10_000)
    assert forever.cooldown_hours() <= DEFAULT_ASK_COOLDOWN_MAX_HOURS


def test_an_artist_that_just_worked_waits_whether_or_not_the_record_landed():
    recorded = AskState("silt", last_event="recorded")
    accepted = AskState("silt", last_event="accepted")  # said yes; record failed
    assert recorded.cooldown_hours() == DEFAULT_RECORD_COOLDOWN_HOURS
    assert accepted.cooldown_hours() == DEFAULT_RECORD_COOLDOWN_HOURS


def test_an_artist_nobody_has_ever_asked_is_askable_right_now():
    assert AskState("vess").may_be_asked(NOW)
    assert AskState("vess").ready_at() is None


def test_the_wait_is_measured_from_the_last_answer():
    state = AskState(
        "silt",
        last_event="declined",
        declines=1,
        last_event_at=NOW - timedelta(hours=DEFAULT_ASK_COOLDOWN_HOURS - 1),
    )
    assert not state.may_be_asked(NOW)
    assert state.may_be_asked(NOW + timedelta(hours=2))


# --- the state, read back out of the log --------------------------------------


def _asked(artist: str, ready: bool, hours_ago: float) -> dict:
    return {"kind": "artist_asked", "artist": artist, "ready": ready, "ts": _ts(hours_ago)}


def test_the_conductor_remembers_nothing_the_log_does_not_say():
    rows = [
        _asked("silt", False, 60),
        _asked("silt", False, 30),
        {"kind": "album_completed", "artist": "rust", "ts": _ts(20)},
        _asked("silt", False, 10),
    ]
    states = ask_states(rows, ROSTER)
    assert states["silt"].declines == 3 and states["silt"].last_event == "declined"
    assert states["rust"].last_event == "recorded" and states["rust"].records == 1
    assert states["keep"].last_event == "" and states["keep"].asks == 0


def test_a_yes_or_a_record_resets_the_streak():
    rows = [_asked("silt", False, 90), _asked("silt", False, 80), _asked("silt", True, 70)]
    assert ask_states(rows, ROSTER)["silt"].declines == 0
    rows.append({"kind": "album_completed", "artist": "silt", "ts": _ts(69)})
    after = ask_states(rows, ROSTER)["silt"]
    assert after.declines == 0 and after.records == 1


def test_a_smoke_is_a_rehearsal_and_never_counts_as_an_answer():
    rows = [{**_asked("silt", False, 5), "smoke": True}]
    assert ask_states(rows, ROSTER)["silt"].last_event == ""


def test_who_may_be_asked_is_exactly_who_is_out_of_cooldown():
    rows = [
        _asked("silt", False, 1),  # 12h wait, 1h in — not yet
        _asked("rust", False, 20),  # 12h wait, 20h in — ready
        {"kind": "album_completed", "artist": "keep", "ts": _ts(2)},  # 24h wait
    ]
    states = ask_states(rows, ROSTER)
    assert set(askable(states, NOW)) == {"rust", "vess", "lolgorithm"}


def test_a_quiet_artist_and_a_prolific_one_can_coexist_forever():
    """No fairness rule: a decliner drifts to weekly asks while a worker is
    back in the room a day later, and neither state pushes the other."""
    rows = [_asked("silt", False, h) for h in (400, 300, 200, 100, 1)]
    rows += [{"kind": "album_completed", "artist": "rust", "ts": _ts(25)}]
    states = ask_states(rows, ROSTER)
    assert states["silt"].cooldown_hours() == DEFAULT_ASK_COOLDOWN_MAX_HOURS
    assert "rust" in askable(states, NOW) and "silt" not in askable(states, NOW)


# --- the order ----------------------------------------------------------------


def test_the_knocking_order_is_seeded_and_is_not_alphabetical():
    import random

    order = ask_order(ROSTER, random.Random(7))
    assert sorted(order) == sorted(ROSTER)
    assert order == ask_order(ROSTER, random.Random(7))  # a replayed tick replays
    shuffles = {tuple(ask_order(ROSTER, random.Random(s))) for s in range(30)}
    assert len(shuffles) > 1, "the order never varies"
    # Over many ticks every artist reaches the front — position on the roster
    # is not a privilege.
    firsts = {ask_order(ROSTER, random.Random(s))[0] for s in range(200)}
    assert firsts == set(ROSTER)
