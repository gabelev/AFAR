"""Booking: who records next, and how big the record is.

The album is the unit of work (docs/SPEC.md), so the conductor's loop books
ALBUMS: one artist, one record. Two mechanical decisions per booking, both
pure and both here so they can be tested without a model, a renderer or a
clock:

1. **WHO** — `book_artist`. Fair rotation across the whole roster: the artist
   who has gone longest without recording goes next, with a little variation
   so the town never metronomes through the alphabet. Deterministic given the
   log: the same recorded history and the same seed always book the same
   artist, which is what makes the rotation testable and what makes a restart
   resume the piece rather than reroll it.

2. **HOW BIG** — `fit_album`. Track count and per-track length come from env
   knobs (`AFAR_ALBUM_TRACKS`, `AFAR_TRACK_SECONDS` — see `afar.config`) and
   are then SHRUNK, mechanically, to whatever is left of the day's
   audio-minutes. No model decides the size of a record: the Producer books
   nothing any more (architecture rule 1), and a budget is arithmetic.

The shrink order is deliberate: **length first, then songs**. A record is a
record because it has songs on it; a tight day should yield shorter songs
before it yields a shorter tracklist, and only a day with almost nothing left
drops to the two-song floor. Below the floor (2 tracks x 30s = 1 audio-minute)
nothing is booked at all and the conductor waits for the next UTC day.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Optional, Sequence

from afar.album import MAX_TRACKS, MIN_TRACKS

#: The renderer's take-length range (`afar.render`, the variable-length entry
#: in DECISIONS.md). A track shorter than 30s is a jingle; longer than 120s
#: is beyond what music_v2 was sized for here.
MIN_TRACK_SECONDS = 30
MAX_TRACK_SECONDS = 120

#: How many of the longest-waiting artists the booking picks between. 1 would
#: be a strict queue (perfectly fair and perfectly predictable — the town would
#: cycle in a fixed order forever); the whole roster would be a lottery that
#: leaves artists silent for months. Three keeps the wait bounded (an artist
#: can be passed over at most twice before it is alone at the front) while the
#: order still surprises.
VARIATION_WINDOW = 3


# --- who records next ---------------------------------------------------------


def rotation_order(roster: Sequence[str], history: Sequence[str]) -> list[str]:
    """The roster sorted by how long since each artist last recorded — longest
    wait first.

    `history` is the artist ids of the albums already recorded, OLDEST FIRST,
    exactly as the log lists them. An artist that has never recorded has waited
    longest of all (a debut outranks any silence), and ties break
    alphabetically so the order is a pure function of its inputs.
    """
    last_seen: dict[str, int] = {}
    for position, artist_id in enumerate(history):
        last_seen[str(artist_id)] = position
    return sorted(roster, key=lambda artist_id: (last_seen.get(artist_id, -1), artist_id))


def _booking_seed(seed: int, index: int) -> int:
    """A stable per-booking seed: the conductor's seed, hash-offset by the
    album index (the `player_seed` idiom — position-stable, so booking N is
    the same draw whether it is reached on the first boot or the fifth)."""
    key = f"booking:{index}".encode("utf-8")
    return seed + int(hashlib.sha256(key).hexdigest()[:8], 16)


def book_artist(
    roster: Sequence[str],
    history: Sequence[str],
    *,
    index: int,
    seed: int = 0,
    window: int = VARIATION_WINDOW,
) -> str:
    """Who records album `index`: one of the `window` longest-waiting artists,
    drawn deterministically from (seed, index).

    Deterministic given the log — the same history, seed and index always
    return the same artist — so the rotation is testable and a restart that
    replays a booking books the same record.
    """
    if not roster:
        raise ValueError("cannot book an album with an empty roster")
    order = rotation_order(roster, history)
    candidates = order[: max(1, min(window, len(order)))]
    return random.Random(_booking_seed(seed, index)).choice(candidates)


# --- how big the record is ----------------------------------------------------


@dataclass(frozen=True)
class AlbumSize:
    """The shape of one booked record: how many songs, and how long each is."""

    tracks: int
    track_seconds: int

    @property
    def minutes(self) -> float:
        return album_minutes(self.tracks, self.track_seconds)


def album_minutes(tracks: int, track_seconds: float) -> float:
    """The audio-minutes one record of this shape will generate — the only
    number the daily cap cares about."""
    return tracks * track_seconds / 60.0


#: The smallest record that is still a record: the track floor at the length
#: floor. Nothing below this is booked; the conductor sleeps to the next day.
FLOOR_MINUTES = album_minutes(MIN_TRACKS, MIN_TRACK_SECONDS)


def fit_album(
    tracks: int, track_seconds: int, remaining_minutes: float
) -> Optional[AlbumSize]:
    """Shrink a wanted record to what the day can still afford.

    Length shrinks first (down to `MIN_TRACK_SECONDS`), then the tracklist
    (down to `MIN_TRACKS`). Returns None when not even the floor record fits —
    the honest answer is "not today", not a one-song single nobody asked for.
    Never grows a record: the env knobs are what the piece wants, and a fat
    budget is not a reason to make a longer record than the piece wants.
    """
    tracks = max(MIN_TRACKS, min(MAX_TRACKS, int(tracks)))
    track_seconds = max(MIN_TRACK_SECONDS, min(MAX_TRACK_SECONDS, int(track_seconds)))
    if remaining_minutes + 1e-9 < FLOOR_MINUTES:
        return None
    budget_seconds = remaining_minutes * 60.0
    while tracks >= MIN_TRACKS:
        fitted = int(budget_seconds // tracks)
        if fitted >= MIN_TRACK_SECONDS:
            return AlbumSize(tracks=tracks, track_seconds=min(track_seconds, fitted))
        tracks -= 1
    return None
