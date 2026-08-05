"""The ask: does this artist have a record in it right now?

The conductor stopped booking. It does not decide who makes art any more —
it keeps time, it meters the money, and it knocks on doors. What happens
behind the door is the artist's (docs/SPEC.md, "the law: artists decide when
they record").

Two pure things live here, both testable without a model, a clock or a log
reader:

1. **`Urge`** — the answer: `{ready: bool, why: str}`, parsed tolerantly out
   of whatever shape a cheap model actually emits (fences, prose wrappers,
   "yes"/"no" in place of a bool). A reply with no `why` is unusable: the
   distribution of who says no and why is the whole observable of this
   change, so an answer that will not say why is worth re-asking for.

2. **The cooldown** — how long an artist is left alone after it answers.
   Derived entirely from the append-only log (`ask_states`), so the
   conductor remembers nothing across restarts, exactly like the booking it
   replaced.

THE CURVE, and why it is shaped like this. Cooldown grows with CONSECUTIVE
declines and is capped:

    declines   1     2     3     4     5+
    wait      12h   24h   48h   96h   168h (the cap)

- A first "not yet" means *not right now*, not *not ever* — half a day is a
  fair pause before knocking again, roughly one turn of the piece's day.
- Doubling is the lesson the failure backoff already learned: the more times
  a signal repeats, the less new information the next sample carries. An
  artist in a fallow season should not be pestered every three hours; the
  asks it does get should land far enough apart that something could
  plausibly have changed between them.
- The cap is one week, and it is the important half. Uncapped doubling
  silences a quiet artist permanently inside a month — which would be the
  conductor deciding, by arithmetic, that this artist is done. Capped, EVERY
  artist on the roster is asked at least weekly forever, so a season of
  silence can always end on its own.
- An artist that just answered YES waits `record_hours` (default a day),
  whether or not the record actually got made. A record is a big thing to
  have just done; and if the record failed, one day is a short enough leash
  that nothing is lost while 24 other doors are still open.

There is deliberately NO fairness rule and NO rotation here. Cooldowns are
the only structure, and every one of them is derived from that artist's own
answers. If a prolific act records weekly for a month while another says no
every time it is asked, that is the piece working.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from afar.intent import _loads_lenient

#: The first decline's wait, in hours (AFAR_ASK_COOLDOWN_HOURS).
DEFAULT_ASK_COOLDOWN_HOURS = 12.0
#: The ceiling on the doubling (AFAR_ASK_COOLDOWN_MAX_HOURS) — one week, so
#: nobody is ever silenced by arithmetic.
DEFAULT_ASK_COOLDOWN_MAX_HOURS = 168.0
#: The wait after an artist says yes (AFAR_RECORD_COOLDOWN_HOURS).
DEFAULT_RECORD_COOLDOWN_HOURS = 24.0
#: The wait after a yes whose record then FAILED (AFAR_FAILED_COOLDOWN_HOURS).
#: Short on purpose: the artist had a record in it and a timeout took the
#: slot, so the yes is not spent — but a long enough pause that an artist
#: whose records keep failing cannot spin the loop. The conductor's own
#: failure backoff paces the retries globally either way.
DEFAULT_FAILED_COOLDOWN_HOURS = 1.0

#: How many doors the conductor knocks on per tick before letting the tick go
#: (AFAR_ASKS_PER_TICK). It stops at the first yes: the budget, the renderer
#: and the publish path are all one record at a time.
DEFAULT_ASKS_PER_TICK = 3
#: Ticks per UTC day (AFAR_ASKS_PER_DAY) — the conductor's clock, not a quota.
DEFAULT_ASKS_PER_DAY = 8.0


# --- the answer ---------------------------------------------------------------


_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0", "not yet", "not now"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"`ready` must be true or false, got {value!r}")


@dataclass(frozen=True)
class Urge:
    """One artist's answer to "do you have a record in you right now?"."""

    artist_id: str
    ready: bool
    why: str

    def to_row(self) -> dict[str, Any]:
        return {"artist": self.artist_id, "ready": self.ready, "why": self.why}

    @classmethod
    def from_json(cls, text: str, *, artist_id: str) -> "Urge":
        """Parse a model reply into an Urge, or raise ValueError.

        Tolerant about shape (fences, a prose wrapper, "yes"/"no" for the
        bool) and strict about substance: an answer with no `why` is refused,
        because the reason is the thing the piece is here to record.
        """
        data = _loads_lenient(text)
        if not isinstance(data, Mapping):
            raise ValueError("the ask's reply must be a JSON object")
        if "ready" not in data:
            raise ValueError("the ask's reply needs a `ready` field")
        why = str(data.get("why", "")).strip()
        if not why:
            raise ValueError("the ask's reply needs a `why` — say it either way")
        return cls(artist_id=artist_id, ready=_as_bool(data["ready"]), why=why)


# --- the cooldown, read back out of the log -----------------------------------


def _parse_ts(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class AskState:
    """What the log says about one artist's answering history.

    `last_event` is one of "" (never asked, never recorded), "recorded",
    "accepted" (said yes and the record is in flight), "failed" (said yes and
    the record died before it landed) or "declined". `declines` counts
    CONSECUTIVE declines since the last yes or record — the exponent in the
    curve; a failure is not a decline and never touches it.
    """

    artist_id: str
    last_event: str = ""
    last_event_at: Optional[datetime] = None
    declines: int = 0
    asks: int = 0
    records: int = 0

    def cooldown_hours(
        self,
        *,
        base_hours: float = DEFAULT_ASK_COOLDOWN_HOURS,
        max_hours: float = DEFAULT_ASK_COOLDOWN_MAX_HOURS,
        record_hours: float = DEFAULT_RECORD_COOLDOWN_HOURS,
        failed_hours: float = DEFAULT_FAILED_COOLDOWN_HOURS,
    ) -> float:
        """How long this artist is left alone after its last answer."""
        if self.last_event == "failed":
            # A yes that never became a record is not a record. Spending the
            # full day's cooldown on it would let a network timeout silence
            # an artist that had something to make (the-sardis-fasola-society,
            # 2026-08-05, lost its slot to a read timeout).
            return failed_hours
        if self.last_event in ("recorded", "accepted"):
            return record_hours
        if self.last_event == "declined":
            # The exponent is clamped BEFORE it is computed: an artist that
            # has declined a few thousand times is still just "at the cap",
            # and 2**n overflows a float long before it stops being the cap.
            steps = min(max(0, self.declines - 1), 64)
            return min(base_hours * (2**steps), max_hours)
        return 0.0

    def ready_at(self, **kw: float) -> Optional[datetime]:
        """When this artist may be asked again — None means "any time now"."""
        if self.last_event_at is None:
            return None
        return self.last_event_at + timedelta(hours=self.cooldown_hours(**kw))

    def may_be_asked(self, now: datetime, **kw: float) -> bool:
        when = self.ready_at(**kw)
        return when is None or now >= when


def ask_states(
    rows: Sequence[Mapping[str, Any]], roster: Sequence[str]
) -> dict[str, AskState]:
    """Every artist's answering history, rebuilt from the conductor's rows.

    Reads exactly three kinds: `artist_asked` (who was asked, what they said,
    when), `album_completed` (who actually made a record) and `album_failed`
    (whose record died on the way). Rows are taken in log order; a yes or a
    finished record resets the decline streak, and a failure leaves it alone.
    Smoke rows never count — a rehearsal is not an answer.
    """
    states = {artist_id: AskState(artist_id=artist_id) for artist_id in roster}
    for row in rows:
        if row.get("smoke"):
            continue
        kind = str(row.get("kind", ""))
        artist_id = str(row.get("artist", ""))
        if artist_id not in states:
            continue
        stamp = _parse_ts(row.get("ts"))
        state = states[artist_id]
        if kind == "artist_asked":
            ready = bool(row.get("ready"))
            states[artist_id] = AskState(
                artist_id=artist_id,
                last_event="accepted" if ready else "declined",
                last_event_at=stamp or state.last_event_at,
                declines=0 if ready else state.declines + 1,
                asks=state.asks + 1,
                records=state.records,
            )
        elif kind == "album_failed":
            # The yes stands: this artist is asked again shortly, and may
            # still have the same record in it.
            states[artist_id] = AskState(
                artist_id=artist_id,
                last_event="failed",
                last_event_at=stamp or state.last_event_at,
                declines=state.declines,
                asks=state.asks,
                records=state.records,
            )
        elif kind == "album_completed":
            states[artist_id] = AskState(
                artist_id=artist_id,
                last_event="recorded",
                last_event_at=stamp or state.last_event_at,
                declines=0,
                asks=state.asks,
                records=state.records + 1,
            )
    return states


def askable(states: Mapping[str, AskState], now: datetime, **kw: float) -> list[str]:
    """Everyone whose cooldown has run out, in the states' own order."""
    return [
        artist_id for artist_id, state in states.items() if state.may_be_asked(now, **kw)
    ]


def ask_order(candidates: Sequence[str], rng: random.Random) -> list[str]:
    """The order the conductor knocks in — shuffled, so the town is never
    walked alphabetically and no position on the roster is a privilege.

    Deterministic given the rng (the conductor seeds it per tick from the
    schedule's position-stable seed), so a replayed tick knocks in the same
    order — the property the old booking draw had, without the fairness.
    """
    order = list(candidates)
    rng.shuffle(order)
    return order
