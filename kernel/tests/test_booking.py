"""Booking: who records next, and how big the record is.

Both halves are pure (`afar.booking`), and both are load-bearing: the rotation
is the only thing that decides whose voice the town hears next, and the sizing
is the only thing standing between the piece and its ElevenLabs bill.
"""

from __future__ import annotations

import pytest

from afar.album import MAX_TRACKS, MIN_TRACKS
from afar.booking import (
    FLOOR_MINUTES,
    MAX_TRACK_SECONDS,
    MIN_TRACK_SECONDS,
    album_minutes,
    book_artist,
    fit_album,
    rotation_order,
)

ROSTER = ("silt", "rust", "keep", "vess", "lolgorithm")


# --- who records next ---------------------------------------------------------


def test_rotation_puts_the_longest_wait_first_and_a_debut_ahead_of_everyone():
    # silt recorded most recently, keep before that; vess/lolgorithm never have.
    order = rotation_order(ROSTER, ["rust", "keep", "rust", "silt"])
    assert order[:2] == ["lolgorithm", "vess"]  # never recorded, alphabetical
    assert order[2:] == ["keep", "rust", "silt"]  # then by how long ago


def test_rotation_is_a_pure_function_of_its_inputs():
    history = ["keep", "silt", "rust"]
    assert rotation_order(ROSTER, history) == rotation_order(ROSTER, history)
    assert rotation_order(tuple(reversed(ROSTER)), history) == rotation_order(ROSTER, history)


def test_booking_is_deterministic_given_the_log_and_varies_with_position():
    history = ["silt", "rust"]
    picks = [book_artist(ROSTER, history, index=i, seed=7) for i in range(12)]
    again = [book_artist(ROSTER, history, index=i, seed=7) for i in range(12)]
    assert picks == again, "the same log and seed must book the same artist"
    # Variation is the point of the window: the same standings do not always
    # yield the same name.
    assert len(set(picks)) > 1


def test_booking_only_ever_picks_from_the_longest_waiting_window():
    history = ["a", "b", "c", "d", "e"]
    roster = ["a", "b", "c", "d", "e", "f"]
    front = set(rotation_order(roster, history)[:3])
    for i in range(40):
        assert book_artist(roster, history, index=i, seed=3) in front


def test_an_artist_cannot_be_passed_over_forever():
    """The window bounds the wait: whoever is at the front stays at the front
    until they record, and with a window of 3 they can be skipped at most
    twice before they are the only candidate left."""
    roster = list("abcde")
    history: list[str] = []
    waited = {a: 0 for a in roster}
    for i in range(60):
        picked = book_artist(roster, history, index=i, seed=11)
        history.append(picked)
        for a in roster:
            waited[a] = 0 if a == picked else waited[a] + 1
    assert max(waited.values()) <= len(roster) + 2


def test_booking_an_empty_roster_is_an_error_not_a_silent_skip():
    with pytest.raises(ValueError):
        book_artist([], [], index=0)


# --- how big the record is ----------------------------------------------------


def test_a_full_budget_gets_exactly_what_the_knobs_asked_for():
    size = fit_album(4, 120, 110.0)
    assert size == fit_album(4, 120, 110.0)
    assert (size.tracks, size.track_seconds) == (4, 120)
    assert size.minutes == pytest.approx(8.0)


def test_a_fat_budget_never_grows_the_record():
    """The knobs are what the piece WANTS; spare budget is not a reason to
    make a longer record than the piece wants."""
    assert fit_album(3, 60, 10_000.0) == fit_album(3, 60, 10.0)


def test_length_shrinks_before_the_tracklist_does():
    size = fit_album(4, 120, 5.0)  # 5 minutes over 4 songs = 75s each
    assert (size.tracks, size.track_seconds) == (4, 75)


def test_the_tracklist_shrinks_only_when_the_length_floor_is_reached():
    # 1.5 min: 4 x 30s needs 2 min, 3 x 30s needs 1.5 — the tracklist gives.
    size = fit_album(4, 120, 1.5)
    assert (size.tracks, size.track_seconds) == (3, 30)


def test_nothing_is_booked_below_the_floor_record():
    assert fit_album(4, 120, FLOOR_MINUTES - 0.01) is None
    assert fit_album(4, 120, 0.0) is None
    floor = fit_album(4, 120, FLOOR_MINUTES)
    assert (floor.tracks, floor.track_seconds) == (MIN_TRACKS, MIN_TRACK_SECONDS)


def test_the_knobs_are_clamped_to_the_contracts_they_have_to_satisfy():
    """A misconfigured env must never produce a record `Album.validate` or the
    renderer would refuse."""
    big = fit_album(99, 9999, 10_000.0)
    assert big.tracks == MAX_TRACKS and big.track_seconds == MAX_TRACK_SECONDS
    small = fit_album(0, 1, 10_000.0)
    assert small.tracks == MIN_TRACKS and small.track_seconds == MIN_TRACK_SECONDS


def test_a_booked_record_never_overruns_what_is_left():
    for remaining in (1.0, 1.7, 3.3, 8.0, 12.5, 109.9):
        size = fit_album(4, 120, remaining)
        if size is None:
            assert remaining < FLOOR_MINUTES
        else:
            assert size.minutes <= remaining + 1e-9
            assert album_minutes(size.tracks, size.track_seconds) == size.minutes
