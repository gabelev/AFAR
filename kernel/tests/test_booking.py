"""Sizing: how big a record is allowed to be.

Pure (`afar.booking`) and load-bearing: it is the only thing standing between
the piece and its ElevenLabs bill. WHO records is not decided here any more
and is not decided anywhere in the conductor — the artists decide
(`tests/test_asking.py`, `tests/test_ask_loop.py`).
"""

from __future__ import annotations

import pytest

from afar.album import MAX_TRACKS, MIN_TRACKS
from afar.booking import (
    FLOOR_MINUTES,
    MAX_TRACK_SECONDS,
    MIN_TRACK_SECONDS,
    album_minutes,
    fit_album,
)


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
