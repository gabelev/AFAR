"""Booking: how big the record is.

The album is the unit of work (docs/SPEC.md), and WHO records is no longer
decided here — or anywhere in the conductor. Artists decide that themselves
(`afar.asking`, `Player.consider_record`); the conductor keeps time and meters
the money. What survives is the one decision that was always mechanical:

**HOW BIG** — `fit_album`. Track count and per-track length come from env
knobs (`AFAR_ALBUM_TRACKS`, `AFAR_TRACK_SECONDS` — see `afar.config`) and are
then SHRUNK, mechanically, to whatever is left of the day's audio-minutes. No
model decides the size of a record: the Producer books nothing (architecture
rule 1), the artist decides whether to work at all, and a budget is
arithmetic.

The shrink order is deliberate: **length first, then songs**. A record is a
record because it has songs on it; a tight day should yield shorter songs
before it yields a shorter tracklist, and only a day with almost nothing left
drops to the two-song floor. Below the floor (2 tracks x 30s = 1 audio-minute)
nothing is made at all and the conductor waits for the next UTC day — no
artist is even asked, because a yes it could not honour would be a lie.

(`book_artist`/`rotation_order` lived here until the loop stopped booking.
They were fair rotation across the whole roster, and fairness is exactly what
artist agency replaces: see DECISIONS.md, 2026-08-04.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from afar.album import MAX_TRACKS, MIN_TRACKS

#: The renderer's take-length range (`afar.render`, the variable-length entry
#: in DECISIONS.md). A track shorter than 30s is a jingle; longer than 120s
#: is beyond what music_v2 was sized for here.
MIN_TRACK_SECONDS = 30
MAX_TRACK_SECONDS = 120

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
