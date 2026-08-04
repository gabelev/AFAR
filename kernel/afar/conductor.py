"""The conductor: the thin continuous loop that makes AFAR run forever.

    uv run python -m afar.conductor            # the piece (systemd runs this)
    uv run python -m afar.conductor --smoke    # one small album, publish dry-run
    uv run python -m afar.conductor --once     # one booked album, then exit

THE LOOP BOOKS ALBUMS. The album is AFAR's unit of work (docs/SPEC.md), so
one turn of the live loop is one artist making one whole record:

    book (who + how big)  ->  run_album  ->  PUBLISH  ->  the staff react

- **Who** is fair rotation across the whole 25-artist roster: the artist who
  has gone longest without recording, drawn from the three longest-waiting so
  the town never metronomes through the alphabet. Deterministic given the log
  (`afar.booking.book_artist`), so a restart resumes the piece rather than
  rerolling it.
- **How big** is MECHANICAL, never a model's call: `AFAR_ALBUM_TRACKS` songs
  of `AFAR_TRACK_SECONDS` each, shrunk to whatever is left of the day's
  audio-minutes (`afar.booking.fit_album` — length first, then the tracklist,
  and nothing at all below the two-song floor). The Producer books nothing
  any more; a budget is arithmetic.
- **What the artist hears** is read back out of the log every time
  (`afar.album_log`): the most recent record by each of the last few other
  artists to release, plus its own last one, every sleeve crossing through
  `heard_album_from_row`'s whitelist. The conductor remembers nothing.
- **Publish comes BEFORE the reactions**, and that ordering is the law in
  code: `run_reactions` refuses to run without the release id of a record
  that already exists (architecture rule 1 — staff never touch the artifact).
  The record goes out, the staff react to a public record, and a second
  idempotent publish hangs their words off the same catalogue number.

The conductor stays thin: `afar.booking` decides, `afar.album_log` reads,
`run_album` makes the record, `afar.publish` ships it, `run_reactions` walks
the staff. This module only WALKS that plan, meters the spend and paces.

THE EXPERIMENT INSTRUMENT (AFAR_EXPERIMENT_MODE=1) runs the ROUND-BASED SET
loop instead, unchanged: three house acts, rounds, the schedule's 3:1:1
condition draw, the Producer's direction and cut, the Critic's naming, the
session tape. That is the offline experiment and the code that reproduces the
logged round-based history (releases 0001-0007, TAPE-0001..0017). The live
loop simply never books a set.

THE SCHEDULE still keeps the piece's time in both modes: eras, era stances
and the position-stable seed come from `afar.schedule` indexed by the album
(or set) number, so the piece's slow clocks are unchanged by the new spine.

SPEND CONTROL (hard, by design):

  - AFAR_ENABLED is the master switch and ships "0": the loop idles, writing
    a `disabled` heartbeat row once an hour — an idle conductor is a healthy
    conductor, and the health timer reads exactly those rows.
  - AFAR_DAILY_AUDIO_MINUTES is a hard ceiling on generated audio-MINUTES per
    UTC day (110 by default — the $500/mo sizing). Minutes, not generation
    counts, are what cost money. The meter lives in a state file
    (runs/conductor/gen_budget.json) so restarts cannot reset spend; the
    generation COUNT rides along as telemetry. An album's whole projected
    spend is charged BEFORE the first render, so a crash mid-record can never
    under-count what was already paid for; at the cap the conductor books
    nothing and sleeps to the next UTC day. Old {day, generations} state
    files migrate on read (minutes estimated at 0.5/generation — every
    pre-migration take was 30s).
  - AFAR_ALBUMS_PER_DAY paces the live loop (AFAR_SETS_PER_DAY paces the
    experiment loop): after each record, sleep so the daily count lands near
    the target, with +/-20% jitter so the piece never metronomes.
  - The ElevenLabs 2-slot concurrency semaphore stays in-process: the
    conductor is a single process (systemd Type=simple, one instance), so a
    process-local semaphore IS the global one. A second kernel writer would
    need the cluster lease DECISIONS.md already flags.

DURABILITY: each album runs under try/except — a failure logs an
`album_failed` row to the conductor ledger, checkpoints, and the loop
continues with the next booking (the rotation reads the log, so a failed
booking simply never enters the history and that artist stays at the front of
the queue). `album_failed` is reserved for the RECORD failing: a published
album is never voided by a staff failure. Reaction stages degrade
individually inside `run_reactions` (the material always outranks the
commentary), the record stays out, and the conductor logs a `staff_degraded`
row naming which reactions went absent.
A failed album does NOT wait out the full pace interval: the next attempt
comes after a short failure backoff (AFAR_FAILURE_BACKOFF_MIN, default 15
minutes, doubling per consecutive failure, capped at the pace interval; a
completed album resets it) — the daily minutes cap still governs, since a
failed album spends real audio-minutes.
On boot the conductor resumes idempotently from the JSONL cursor: the highest
index with an `album_completed`/`album_failed` row, plus one.
SIGTERM finishes the CURRENT RECORD and exits 0 between albums — the unit of
work is the album now, so that is the unit the stop respects; a record is
never left half-made, and the cursor advances only on a record that finished.
(The round-based loop's mid-set `after_round` abort survives in the
experiment path, where a set is hours long and a round is the natural seam.)

ERA BOUNDARIES are the only place slow state moves: on the frame between two
eras the FieldTabooMemory rolls over (a hostile era's observed field moves
carry exactly one era) and every artist's SelfState is bumped —
`persona_state` rows log each bump, and on boot the conductor rebuilds each
artist's version/residue from those rows, so drift survives restarts.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from ensemble.agent import SelfState

from afar import album_log
from afar.agents.muse import Brief
from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.agents.producer import (
    DEFAULT_SESSION_FORM,
    SESSION_FORM_CONDITIONS,
    ProducerAgent,
)
from afar.album import MIN_TRACKS
from afar.booking import MIN_TRACK_SECONDS, AlbumSize, book_artist, fit_album
from afar.config import AfarConfig, build_config
from afar.intent import PLAYER_IDS
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import AudioEmbedder, MockEmbedder
from afar.run import SetAborted, run_album, run_set
from afar.schedule import Schedule, ScheduleConfig, SetPlan
from afar.staff import (
    artist_display_name,
    load_recent_reactions,
    run_reactions,
    run_staff,
)
from afar.state.field_taboo import FieldTabooMemory

SECONDS_PER_DAY = 86_400
HEARTBEAT_SECONDS = 3_600  # one heartbeat/disabled row per hour, at most
_JITTER = 0.20

CONDUCTOR_RUN_ID = "conductor"  # runs/conductor/{conductor.jsonl,eras.jsonl,gen_budget.json}


# --- pure pacing + cursor math (unit-tested) ----------------------------------


def pace_seconds(elapsed: float, sets_per_day: float, rng: random.Random) -> float:
    """How long to sleep after a set so sets/day lands near the target.

    Base interval = 86400 / sets_per_day, jittered +/-20% so the piece never
    metronomes; the set's own elapsed time counts toward the interval. Never
    negative — a set slower than the interval just rolls straight on.
    """
    if sets_per_day <= 0:
        raise ValueError(f"sets_per_day must be > 0, got {sets_per_day}")
    base = SECONDS_PER_DAY / sets_per_day
    jittered = base * rng.uniform(1.0 - _JITTER, 1.0 + _JITTER)
    return max(0.0, jittered - max(0.0, elapsed))


def failure_backoff_seconds(
    consecutive_failures: int, backoff_min: float, sets_per_day: float
) -> float:
    """How long to sleep after a failed set: backoff_min minutes, doubling per
    consecutive failure (15/30/60/...), capped at the unjittered pace interval
    — a transient outage gets a fast second chance instead of the full ~8h
    wait, while a persistent one degrades to normal pacing. The daily
    minutes cap still governs spend on every attempt."""
    if consecutive_failures < 1:
        raise ValueError(f"consecutive_failures must be >= 1, got {consecutive_failures}")
    if sets_per_day <= 0:
        raise ValueError(f"sets_per_day must be > 0, got {sets_per_day}")
    backoff = backoff_min * 60.0 * (2 ** (consecutive_failures - 1))
    return min(backoff, SECONDS_PER_DAY / sets_per_day)


def next_set_index(rows: list[Mapping[str, Any]]) -> int:
    """The JSONL cursor: resume after the highest set a conductor row closed
    (`set_completed` or `set_failed` — a failed set is skipped, not retried
    forever). Aborted sets (SIGTERM) do NOT advance the cursor: they replay."""
    closed = [
        int(row["set_index"])
        for row in rows
        if row.get("kind") in ("set_completed", "set_failed") and "set_index" in row
    ]
    return (max(closed) + 1) if closed else 0


def next_album_index(rows: Sequence[Mapping[str, Any]]) -> int:
    """The album loop's cursor: resume after the highest index a conductor row
    closed (`album_completed` or `album_failed`).

    The index is a POSITION in the piece, not an identity: it is what the era
    clock and the booking draw are keyed on, so it has to advance past a
    failed record the same way it advances past a finished one. Who records
    is decided from the log's actual history, so a failed booking leaves that
    artist exactly where it was — at the front of the queue.
    """
    closed = [
        int(row["album_index"])
        for row in rows
        if row.get("kind") in ("album_completed", "album_failed") and "album_index" in row
    ]
    return (max(closed) + 1) if closed else 0


#: Plain words for a logged condition — what a session's form is called when
#: the Producer is told what the last few sessions were. "parallel" appears
#: only in history (the town's one lab session, and experiment-mode runs).
FORM_BY_CONDITION: dict[str, str] = {
    "contact": "together",
    "isolation": "alone",
    "parallel": "side by side, unable to hear each other",
}


def recent_session_forms(rows: Sequence[Mapping[str, Any]], limit: int = 4) -> list[str]:
    """The last few sessions' forms, oldest first, read from the conductor's
    own `set_started` rows (the log is the memory) — the variety pressure the
    Producer's booking call weighs. Smoke rows never count: a rehearsal is
    not a session."""
    conditions = [
        str(row["condition"])
        for row in rows
        if row.get("kind") == "set_started" and "condition" in row and not row.get("smoke")
    ]
    return [FORM_BY_CONDITION.get(c, c) for c in conditions[-limit:]]


def seconds_to_next_utc_day(now: datetime) -> float:
    """Sleep-to-the-cap horizon: seconds until the next 00:00 UTC."""
    tomorrow = (now.astimezone(timezone.utc) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1.0, (tomorrow - now.astimezone(timezone.utc)).total_seconds())


#: Migration estimate for pre-minutes state files: every old generation was a
#: 30-second take, i.e. half an audio-minute.
_LEGACY_MINUTES_PER_GENERATION = 0.5


def set_minutes(rounds: int, players: int, duration_s: float) -> float:
    """The whole-set audio-minute projection: every round renders one take
    per player, each `duration_s` long."""
    return rounds * players * duration_s / 60.0


def fit_duration_s(duration_s: int, rounds: int, players: int, remaining_minutes: float) -> int:
    """Clamp the Producer's chosen take length so the WHOLE set's projected
    minutes fit under what remains of the day's budget. Never below 30 (the
    floor take): if even 30s takes don't fit, the pre-set gate — which
    projects at the 30s floor — refuses the set before this runs."""
    takes = rounds * players
    if takes <= 0:
        return duration_s
    max_fit = int(remaining_minutes * 60.0 // takes)
    return max(30, min(duration_s, max_fit))


class GenBudget:
    """The persistent daily audio-minutes meter — the hard cap's memory.

    State file (JSON: {"day": "YYYY-MM-DD", "minutes": M, "generations": N})
    lives under runs/conductor/ so restarts cannot reset spend. MINUTES are
    the gate; the generation count rides along as telemetry. The day is UTC;
    a new day resets both on first read. An old {day, generations} file
    (the generation-cap era) migrates gracefully: the count is preserved and
    minutes are estimated at 0.5 per generation (every old take was 30s).
    """

    def __init__(
        self,
        state_path: Path,
        minutes_cap: float,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.state_path = Path(state_path)
        self.minutes_cap = minutes_cap
        self.clock = clock

    def _today(self) -> str:
        return self.clock().astimezone(timezone.utc).date().isoformat()

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if state.get("day") != self._today():
            return {"day": self._today(), "minutes": 0.0, "generations": 0}
        generations = int(state.get("generations", 0))
        if "minutes" not in state:
            # Same-day migration from the generation-cap format.
            state["minutes"] = generations * _LEGACY_MINUTES_PER_GENERATION
        state["minutes"] = float(state["minutes"])
        state["generations"] = generations
        return state

    @property
    def spent_minutes(self) -> float:
        return float(self._load()["minutes"])

    @property
    def generations_today(self) -> int:
        """Telemetry only — never a gate."""
        return int(self._load()["generations"])

    @property
    def remaining_minutes(self) -> float:
        return max(0.0, self.minutes_cap - self.spent_minutes)

    def would_exceed(self, minutes: float) -> bool:
        """True when spending `minutes` more would break the cap."""
        return self.spent_minutes + minutes > self.minutes_cap + 1e-9

    def add(self, *, generations: int, minutes: float) -> float:
        """Record spend (persisted immediately) and return today's minutes."""
        state = self._load()
        state["generations"] = int(state["generations"]) + generations
        state["minutes"] = round(float(state["minutes"]) + minutes, 6)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
        return state["minutes"]


# --- era drift: what an act kept singing about --------------------------------


def top_obsessions(tag_lists: Sequence[Sequence[str]], limit: int = 3) -> list[str]:
    """The most-recurring lyricalObsessions tags across an era's intents.

    Pure: counts case-insensitively (first-seen casing wins), breaks ties by
    first appearance, returns at most `limit` tags. This is what a player's
    SelfState.obsessions is seeded from at an era boundary — drift grown from
    what the act actually kept returning to, not authored."""
    counts: dict[str, int] = {}
    first_casing: dict[str, str] = {}
    first_seen: dict[str, int] = {}
    for tags in tag_lists:
        for tag in tags:
            text = str(tag).strip()
            key = text.lower()
            if not key:
                continue
            if key not in counts:
                counts[key] = 0
                first_casing[key] = text
                first_seen[key] = len(first_seen)
            counts[key] += 1
    ranked = sorted(counts, key=lambda k: (-counts[k], first_seen[k]))
    return [first_casing[k] for k in ranked[:limit]]


# --- the newest brief (the log is the memory) ---------------------------------


def load_newest_brief(runs_root: Path) -> Optional[Brief]:
    """The Muse's most recent logged brief across ALL runs — what the Producer
    consumes at the next set's start. Read from the log, never remembered:
    a fresh process on a fresh machine directs from the same brief."""
    newest: Optional[Mapping[str, Any]] = None
    root = Path(runs_root)
    if root.exists():
        for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            path = run_dir / "briefs.jsonl"
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("kind") != "brief":
                    continue
                if newest is None or str(row.get("ts", "")) > str(newest.get("ts", "")):
                    newest = row
    if newest is None:
        return None
    return Brief(
        stance=str(newest.get("stance", "")),
        theme=str(newest.get("theme", "")),
        body=str(newest.get("text", "")),
        palette_notes=tuple(newest.get("palette_notes", ())),
        forbidden_moves=tuple(newest.get("forbidden_moves", ())),
        sources=tuple(newest.get("sources", ())),
        thin=bool(newest.get("thin", False)),
        carried_forward=bool(newest.get("carried_forward", False)),
    )


# --- the conductor ------------------------------------------------------------


@dataclass
class SetOutcome:
    """What one walked set produced — for logs and the smoke report."""

    set_index: int
    run_id: str
    completed: bool
    condition: str = ""  # what the session actually ran as (the booking, or the draw)
    released: bool = False
    publish: Optional[Mapping[str, Any]] = None
    error: Optional[str] = None
    staff_degraded: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlbumBooking:
    """One booked record before it exists: who, when, how big, under what seed."""

    index: int
    artist_id: str
    era: int
    stance: str
    seed: int
    size: AlbumSize
    run_id: str
    isolated: bool = False  # the experiment's control, never booked live

    @property
    def minutes(self) -> float:
        return self.size.minutes


@dataclass
class AlbumOutcome:
    """What one booked record produced — for logs and the --once report."""

    index: int
    run_id: str
    artist_id: str
    completed: bool
    album_id: str = ""
    release_id: str = ""
    title: str = ""
    publish: Optional[Mapping[str, Any]] = None
    staff_degraded: tuple[str, ...] = ()
    error: Optional[str] = None


class Conductor:
    """The thin loop. Everything heavy is injected or already exists."""

    def __init__(
        self,
        config: AfarConfig,
        *,
        schedule: Optional[Schedule] = None,
        embedder: Optional[AudioEmbedder] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        rounds_override: Optional[int] = None,
        smoke: bool = False,
    ) -> None:
        self.config = config
        self.schedule = schedule or Schedule(ScheduleConfig())
        # LAZY: building the embedder can mean loading MERT (torch, ~700MB) —
        # a disabled conductor must idle at zero weight, so nothing heavy
        # happens until a set actually plays.
        self._embedder: Optional[AudioEmbedder] = embedder
        self._sleep = sleep
        self.clock = clock
        self.rounds_override = rounds_override
        self.smoke = smoke
        self.rng = random.Random()

        self.ledger = JsonlLedger(
            config.runs_root, CONDUCTOR_RUN_ID, context=RunContext(code_sha=config.code_sha)
        )
        self.budget = GenBudget(
            self.ledger.run_dir / "gen_budget.json", config.daily_audio_minutes, clock=clock
        )
        # The current set's take length (the Producer's direction; 30 until
        # a direction says otherwise) — what _after_round meters spend with.
        self._set_duration_s = 30
        self.players = [Player(PERSONAS[pid], config.model, config.renderer) for pid in PLAYER_IDS]
        self.producer = ProducerAgent(config.model)
        self._artists: dict[str, Player] = {
            pid: player
            for pid, player in zip(PLAYER_IDS, self.players)
        }
        self._restore_persona_state()

        self._stop = False
        self._last_beat = 0.0
        self._consecutive_failures = 0  # in-memory: a restart retries promptly anyway
        rows = self._rows()
        self.set_index = next_set_index(rows)
        self.album_index = next_album_index(rows)
        self.taboo = FieldTabooMemory(
            stance=self.schedule.set_plan(self._index()).era_stance
        )

    def _index(self) -> int:
        """Where the piece is on its clock — the album number live, the set
        number in the experiment. Both index the same `afar.schedule`, so the
        eras, stances and position-stable seeds are the piece's, not a mode's."""
        return self.set_index if self.config.experiment_mode else self.album_index

    # -- the roster: who can be booked ----------------------------------------

    @property
    def roster(self) -> tuple[str, ...]:
        """Every artist the loop may book, in a stable order: the house trio,
        then the committed roster (`afar.agents.roster` — 22 acts, so 25 in
        all). Loaded lazily and ONLY in album mode: the round-based instrument
        plays the house trio, and its `afar.intent` id guard must stay exactly
        those three (the roster loader registers ids as a side effect)."""
        if self.config.experiment_mode:
            return tuple(PLAYER_IDS)
        self._load_roster()
        return tuple(self._artists)

    def _load_roster(self) -> None:
        if len(self._artists) > len(PLAYER_IDS):
            return
        from afar.agents.roster import load_roster

        for artist_id, persona in load_roster().items():
            if artist_id not in self._artists:
                self._artists[artist_id] = Player(persona, self.config.model, self.config.renderer)
        self._restore_persona_state()

    def artist(self, artist_id: str) -> Player:
        """The Player for one artist id, house or roster."""
        self._load_roster()
        if artist_id not in self._artists:
            raise KeyError(f"no persona for artist {artist_id!r}")
        return self._artists[artist_id]

    def artist_names(self) -> dict[str, str]:
        """artist id -> the name the room says out loud."""
        return {artist_id: artist_display_name(artist_id) for artist_id in self.roster}

    @property
    def embedder(self) -> AudioEmbedder:
        """Built on first use (see __init__: disabled conductors stay light)."""
        if self._embedder is None:
            self._embedder = _build_embedder(self.config)
        return self._embedder

    # -- conductor ledger helpers ---------------------------------------------

    def _rows(self) -> list[dict[str, Any]]:
        path = self.ledger.run_dir / "conductor.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _log(self, kind: str, **row: Any) -> None:
        self.ledger.write("conductor", {"kind": kind, **({"smoke": True} if self.smoke else {}), **row})

    def _restore_persona_state(self) -> None:
        """Rebuild each artist's drifted SelfState from logged persona_state
        rows — drift survives restarts because the log is the memory. Re-run
        whenever the roster grows, so a lazily-loaded act arrives drifted."""
        latest: dict[str, Mapping[str, Any]] = {}
        for row in self._rows() if hasattr(self, "ledger") else []:
            if row.get("kind") == "persona_state" and row.get("player"):
                latest[row["player"]] = row
        for pid, player in self._artists.items():
            row = latest.get(pid)
            if row:
                player.self_state = SelfState(
                    version=int(row.get("version", 0)),
                    obsessions=list(row.get("obsessions", ())),
                    residue=dict(row.get("residue", {})),
                )

    # -- signals ---------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        def _request_stop(signum: int, _frame: Any) -> None:
            self._stop = True

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

    def _after_round(self, _t: int) -> bool:
        """run_set's per-round seam: meter the round's spend (minutes are the
        gate, generations the telemetry), report whether a stop was requested
        (True -> finish the current round and abort)."""
        self.budget.add(
            generations=len(self.players),
            minutes=set_minutes(1, len(self.players), self._set_duration_s),
        )
        return self._stop

    # -- idling (interruptible, heartbeat-writing) -----------------------------

    def _beat(self, kind: str, **row: Any) -> None:
        now = time.monotonic()
        if now - self._last_beat >= HEARTBEAT_SECONDS or self._last_beat == 0.0:
            self._last_beat = now
            self._log(
                kind,
                enabled=self.config.enabled,
                sets_per_day=self.config.sets_per_day,
                daily_audio_minutes=self.config.daily_audio_minutes,
                minutes_today=round(self.budget.spent_minutes, 2),
                generations_today=self.budget.generations_today,
                **row,
            )

    def _idle(self, seconds: float, beat_kind: str, **beat_row: Any) -> None:
        """Sleep in short slices so SIGTERM lands promptly, writing a
        heartbeat row at most once an hour — the health timer's food."""
        deadline = time.monotonic() + seconds
        while not self._stop:
            self._beat(beat_kind, **beat_row)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._sleep(min(30.0, remaining))

    # -- one set ---------------------------------------------------------------

    def _direct(self, plan: SetPlan, rounds: int) -> Optional[dict[str, Any]]:
        """Set start, frame side: the Producer consumes the Muse's newest
        logged brief, BOOKS THE SESSION (live mode: session_form together/
        alone, weighed against the brief, the fan's last word, and the last
        few sessions — the reasoning lands in this direction row), and sets
        the session's take length against the day's remaining minutes; the
        chosen duration is clamped so the WHOLE set fits under the cap.
        Returns the direction `run_set` will carry as frame (None on a cold
        start: no brief anywhere is a plain note — the first session of a
        world opens on silence, honestly). In experiment mode no booking
        happens here: the schedule's draw is the condition, exactly as
        before."""
        brief = load_newest_brief(self.config.runs_root)
        if brief is None:
            self._log(
                "direction",
                set_index=plan.index,
                has_brief=False,
                note="cold start — no brief logged yet; the acts open on silence",
            )
            return None
        remaining = self.budget.remaining_minutes
        session = None
        if not self.config.experiment_mode:
            reactions = load_recent_reactions(self.config.runs_root, limit=1)
            session = {
                "recent_forms": recent_session_forms(self._rows()),
                "last_reaction": reactions[-1] if reactions else None,
            }
        direction = self.producer.direct(
            brief, remaining_minutes=remaining, session=session
        )
        fitted = fit_duration_s(
            int(direction["duration_s"]), rounds, len(self.players), remaining
        )
        if fitted != direction["duration_s"]:
            direction = {
                **direction,
                "duration_s": fitted,
                "duration_why": (
                    str(direction.get("duration_why", ""))
                    + f" [clamped to {fitted}s: the whole set must fit the day's remaining minutes]"
                ).strip(),
            }
        self._log("direction", set_index=plan.index, has_brief=True, direction=direction)
        return direction

    def _era_intent_tags(self, closing_era: int) -> dict[str, list[list[str]]]:
        """Every artist's lyricalObsessions tag-lists from the closing era's
        completed work, read back from the runs' own logs (the log is the
        memory — a fresh process on a fresh machine drifts identically).
        Reads both spines: `album_completed` rows live, `set_completed` rows
        in the experiment and across the logged round-based history."""
        tags: dict[str, list[list[str]]] = {artist_id: [] for artist_id in self.roster}
        closed = {"album_completed": "album_index", "set_completed": "set_index"}
        for row in self._rows():
            index_key = closed.get(str(row.get("kind")))
            if index_key is None or index_key not in row:
                continue
            if self.schedule.era_of(int(row[index_key])) != closing_era:
                continue
            run_id = str(row.get("run_id", ""))
            path = Path(self.config.runs_root) / run_id / "intents.jsonl"
            if not run_id or not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                intent_row = json.loads(line)
                pid = intent_row.get("player")
                obsessions = intent_row.get("intent", {}).get("lyricalObsessions", [])
                if pid in tags and obsessions:
                    tags[pid].append([str(tag) for tag in obsessions])
        return tags

    def _era_boundary(self, plan: SetPlan) -> None:
        """The only place slow state moves (schedule law): taboo roll-over and
        persona drift, both logged. Drift now carries CONTENT: each player's
        obsessions are seeded from the top-3 recurring lyricalObsessions tags
        of the act's own closing-era intents (top_obsessions), so the
        SelfState line the decide prompt renders says what the act actually
        kept returning to."""
        if not self.schedule.should_roll_taboo(plan.index):
            return
        self.taboo = self.taboo.roll_over(plan.era_stance)
        self.ledger.write(
            "eras",
            {
                "id": f"era-{plan.era}",
                "kind": "era_open",
                "era": plan.era,
                "stance": plan.era_stance,
                "first_set": plan.index,
                "carried_taboo": list(self.taboo.forbidden_now()),
            },
        )
        era_tags = self._era_intent_tags(plan.era - 1)
        for pid in self.roster:
            player = self.artist(pid) if pid not in self._artists else self._artists[pid]
            obsessions = top_obsessions(era_tags.get(pid, ())) or list(
                player.self_state.obsessions
            )
            player.self_state = player.self_state.bumped(
                obsessions=obsessions,
                residue={
                    **dict(player.self_state.residue),
                    "era": plan.era,
                    "stance": plan.era_stance,
                },
            )
            self._log(
                "persona_state",
                player=pid,
                era=plan.era,
                version=player.self_state.version,
                obsessions=list(player.self_state.obsessions),
                residue=dict(player.self_state.residue),
            )

    # -- one album (the live spine) --------------------------------------------

    def book(self, index: int, remaining_minutes: float) -> Optional[AlbumBooking]:
        """Book record `index`: who records, and how big the record is.

        Both halves are mechanical and both are logged. WHO comes from the
        log's own history through `afar.booking.book_artist` (longest wait
        first, drawn from the three longest-waiting, deterministic given the
        history and the schedule seed). HOW BIG is the env knobs shrunk to the
        day's remaining minutes. Returns None when not even the floor record
        fits — the caller sleeps to the next UTC day.
        """
        plan = self.schedule.set_plan(index)
        # A smoke is a rehearsal, not a record: the smallest legal album, so a
        # supervised run exercises the whole chain at floor cost.
        tracks = MIN_TRACKS if self.smoke else self.config.album_tracks
        seconds = MIN_TRACK_SECONDS if self.smoke else self.config.track_seconds
        size = fit_album(tracks, seconds, remaining_minutes)
        if size is None:
            return None
        history = album_log.recorded_history(album_log.album_rows(self.config.runs_root))
        artist_id = book_artist(self.roster, history, index=index, seed=plan.seed)
        prefix = "smoke-" if self.smoke else ""
        return AlbumBooking(
            index=index,
            artist_id=artist_id,
            era=plan.era,
            stance=plan.era_stance,
            seed=plan.seed,
            size=size,
            run_id=(
                time.strftime("%Y%m%d-%H%M%S")
                + f"-{prefix}album-{index:04d}-{artist_id}"
            ),
        )

    def run_one_album(self, booking: AlbumBooking) -> AlbumOutcome:
        """One artist, one record, start to finish: hear -> write -> render ->
        PUBLISH -> the staff react to a record that is already out."""
        rows = album_log.album_rows(self.config.runs_root)
        heard, own_last = album_log.heard_for(
            rows, booking.artist_id, names=self.artist_names()
        )
        ears = album_log.build_ears(self.config.runs_root, rows, booking.artist_id, heard)

        self._log(
            "album_booked",
            album_index=booking.index,
            run_id=booking.run_id,
            artist=booking.artist_id,
            era=booking.era,
            stance=booking.stance,
            tracks=booking.size.tracks,
            track_seconds=booking.size.track_seconds,
            minutes=round(booking.minutes, 3),
            heard=[a.album_id or a.title for a in heard],
            own_last=own_last.album_id if own_last else None,
            seed=booking.seed,
            renderer=self.config.renderer.name,
            embedder=self.embedder.name,
            minutes_today=round(self.budget.spent_minutes, 2),
            generations_today=self.budget.generations_today,
        )
        # Charge the WHOLE record before the first render: a crash mid-album
        # must never leave spend uncounted (the cap is a ceiling, and the safe
        # direction to be wrong in is "already paid for").
        self.budget.add(generations=booking.size.tracks, minutes=booking.minutes)

        ledger = JsonlLedger(
            self.config.runs_root, booking.run_id, context=RunContext(code_sha=self.config.code_sha)
        )
        result = run_album(
            self.artist(booking.artist_id),
            n_tracks=booking.size.tracks,
            duration_s=booking.size.track_seconds,
            config=self.config,
            ledger=ledger,
            embedder=self.embedder,
            seed=booking.seed,
            heard=heard,
            own_last=own_last,
            ears=ears,
            isolated=booking.isolated,
        )

        # PUBLISH FIRST. `run_reactions` refuses to run without the release id
        # of a record that exists, so this ordering is architecture rule 1
        # enforced by the call graph rather than by discipline.
        publish_row = self._publish_album(ledger.run_dir)
        release_id = str(publish_row.get("release_id", ""))

        reactions = self._react(result, booking, release_id=release_id)
        if reactions is not None and reactions.degraded:
            self._log(
                "staff_degraded",
                album_index=booking.index,
                run_id=booking.run_id,
                stages=list(reactions.degraded),
            )
        if reactions is not None:
            # The second hop: the same catalogue number, now wearing the
            # staff's words. Idempotent by run id — nothing is renumbered.
            self._publish_album(ledger.run_dir, release_id=release_id, kind="reactions_published")

        return AlbumOutcome(
            index=booking.index,
            run_id=booking.run_id,
            artist_id=booking.artist_id,
            completed=True,
            album_id=result.album_id,
            release_id=release_id,
            title=result.album.title,
            publish=publish_row,
            staff_degraded=reactions.degraded if reactions is not None else (),
        )

    def _react(
        self, result: Any, booking: AlbumBooking, *, release_id: str
    ) -> Optional[Any]:
        """The staff react to a PUBLISHED record. Never blocks and never
        raises: `run_reactions` already degrades stage by stage, and a total
        failure here (a broken import, a dead provider) leaves the record out
        and unreviewed rather than voiding it — the material always outranks
        the commentary."""
        try:
            return run_reactions(
                result.album,
                run_dir=result.paths["run_dir"],
                config=self.config,
                release_id=release_id or result.album_id,
                artist_name=artist_display_name(booking.artist_id),
                stance=booking.stance,
                heard=result.record.get("heard", ()),
            )
        except Exception as err:  # noqa: BLE001 — commentary never voids material
            self._log(
                "reactions_failed",
                album_index=booking.index,
                run_id=booking.run_id,
                error=f"{type(err).__name__}: {err}"[:300],
            )
            return None

    def _publish_album(
        self,
        run_dir: Path,
        *,
        release_id: Optional[str] = None,
        kind: str = "album_published",
    ) -> dict[str, Any]:
        """Publish one artist's record. DRY-RUN GUARD, unchanged: mock bytes
        must never land in the public media table, so mock runs (and --smoke)
        always publish dry."""
        from afar.publish import publish_album

        dry = self.smoke or self.config.renderer.name == "mock"
        outcome = publish_album(run_dir, release_id=release_id, dry_run=dry)
        row = {
            "release_id": outcome.release_id,
            "artist": outcome.artist_id,
            "title": outcome.title,
            "dry_run": outcome.dry_run,
            "tracks": outcome.tracks,
            "media_bytes": outcome.media_bytes,
            "track_ids": list(outcome.track_ids),
            "reacted": outcome.reacted,
        }
        self._log(kind, run_id=run_dir.name, **row)
        return row

    # -- one set (the experiment instrument) -----------------------------------

    def run_one_set(self, plan: SetPlan) -> SetOutcome:
        """Walk one planned set end to end: direct -> play -> staff -> publish."""
        rounds = self.rounds_override or plan.rounds
        # Set start, frame side: the brief is consumed HERE and only here —
        # and the direction it becomes rides into run_set as frame. Direction
        # comes FIRST because in live mode it carries the booking.
        direction = self._direct(plan, rounds)
        self._set_duration_s = int(direction["duration_s"]) if direction else 30
        if self.config.experiment_mode:
            # The lab: the schedule's deterministic draw books the room.
            condition = plan.condition
            booked_by = "schedule"
        else:
            # The live piece: the Producer books the session. A cold start
            # (no brief, no direction) or a degraded booking call defaults
            # to "together" — the doors open. Parallel is never booked here.
            form = (
                str(direction.get("session_form", DEFAULT_SESSION_FORM))
                if direction
                else DEFAULT_SESSION_FORM
            )
            condition = SESSION_FORM_CONDITIONS.get(form, SESSION_FORM_CONDITIONS["together"])
            booked_by = "producer"
        prefix = "smoke-" if self.smoke else ""
        run_id = (
            time.strftime("%Y%m%d-%H%M%S")
            + f"-{prefix}set-{plan.index:04d}-{condition}"
        )
        self._log(
            "set_started",
            set_index=plan.index,
            run_id=run_id,
            era=plan.era,
            stance=plan.era_stance,
            condition=condition,
            session_form=FORM_BY_CONDITION.get(condition, condition),
            booked_by=booked_by,
            rounds=rounds,
            seed=plan.seed,
            renderer=self.config.renderer.name,
            embedder=self.embedder.name,
            minutes_today=round(self.budget.spent_minutes, 2),
            generations_today=self.budget.generations_today,
        )

        set_ledger = JsonlLedger(
            self.config.runs_root, run_id, context=RunContext(code_sha=self.config.code_sha)
        )
        run_set(
            self.players,
            rounds=rounds,
            condition=condition,
            config=self.config,
            ledger=set_ledger,
            embedder=self.embedder,
            seed=plan.seed,
            after_round=self._after_round,
            direction=direction,
        )

        # The frame: Producer -> Critic -> Muse -> Listener -> Archivist.
        # run_staff degrades per stage internally — a staff failure can no
        # longer void this completed, fully-paid set (the doctrine: the
        # material always outranks the commentary).
        staff = run_staff(
            set_ledger.run_dir, self.config, stance=plan.era_stance, taboo=self.taboo
        )
        if staff.degraded:
            self._log(
                "staff_degraded",
                set_index=plan.index,
                run_id=run_id,
                stages=list(staff.degraded),
            )

        publish_row: Optional[dict[str, Any]] = None
        if staff.released:
            publish_row = self._publish(set_ledger.run_dir)
        else:
            self._log(
                "publish_skipped",
                set_index=plan.index,
                run_id=run_id,
                reason="no release this set (the Producer's verdict stands)",
            )
            # The vault doctrine: the veto stands; the tape survives. A
            # rejected session's FULL tape still publishes (dry under mock —
            # mock bytes never land in the public media table).
            self._publish_tape(set_ledger.run_dir)
        return SetOutcome(
            set_index=plan.index,
            run_id=run_id,
            completed=True,
            condition=condition,
            released=staff.released,
            publish=publish_row,
            staff_degraded=staff.degraded,
        )

    def _publish(self, run_dir: Path) -> dict[str, Any]:
        """Publish the finished release. DRY-RUN GUARD: a mock renderer's bytes
        must never land in the public media table — mock runs (and --smoke)
        always publish dry."""
        from afar.publish import publish_run

        dry = self.smoke or self.config.renderer.name == "mock"
        outcome = publish_run(run_dir, dry_run=dry)
        row = {
            "release_id": outcome.release_id,
            "release_title": outcome.release_title,
            "dry_run": outcome.dry_run,
            "media_bytes": outcome.media,
            "track_ids": list(outcome.track_ids),
            "timeline_blocks": outcome.timeline_blocks,
        }
        if outcome.tape is not None:
            row["tape_id"] = outcome.tape.tape_id
            row["tape_takes"] = outcome.tape.takes
        self._log("published", run_id=run_dir.name, **row)
        return row

    def _publish_tape(self, run_dir: Path) -> Optional[dict[str, Any]]:
        """Publish a session tape ALONE — the no-release path (the Producer's
        veto). Same dry-run guard as _publish; a tape publish failure is
        logged and swallowed (the set already completed honestly)."""
        from afar.publish import publish_tape

        dry = self.smoke or self.config.renderer.name == "mock"
        try:
            outcome = publish_tape(run_dir, dry_run=dry)
        except Exception as err:  # noqa: BLE001 — the tape must never void the set
            self._log(
                "tape_publish_failed",
                run_id=run_dir.name,
                error=f"{type(err).__name__}: {err}"[:300],
            )
            return None
        row = {
            "tape_id": outcome.tape_id,
            "tape_title": outcome.title,
            "dry_run": outcome.dry_run,
            "takes": outcome.takes,
            "media_bytes": outcome.media_bytes,
            "shelved": outcome.shelved,
        }
        self._log("tape_published", run_id=run_dir.name, **row)
        return row

    # -- the loop --------------------------------------------------------------

    def run_forever(self) -> int:
        """Run the piece until stopped. Returns the process exit code (always
        0 — SIGTERM is a clean exit).

        Live: the ALBUM loop. AFAR_EXPERIMENT_MODE=1: the round-based SET
        loop, unchanged — the offline instrument on the same conductor."""
        self._install_signal_handlers()

        if not self.config.enabled:
            # The master switch is off: idle forever, heartbeat hourly.
            # (Flipping AFAR_ENABLED requires a service restart — the switch
            # is read once at boot, deliberately: one process, one config.)
            while not self._stop:
                self._idle(HEARTBEAT_SECONDS, "disabled")
            self._log("stopped", note="SIGTERM while disabled")
            return 0

        self._log(
            "boot",
            mode="set" if self.config.experiment_mode else "album",
            resume_album_index=self.album_index,
            resume_set_index=self.set_index,
            roster=len(self.roster),
            renderer=self.config.renderer.name,
            embedder=self.embedder.name,
            live_model=self.config.live,
        )
        return self._set_loop() if self.config.experiment_mode else self._album_loop()

    def _album_loop(self) -> int:
        """The live loop: book a record, make it, publish it, let the staff
        react, pace, repeat. SIGTERM finishes the current record and exits."""
        while not self._stop:
            plan = self.schedule.set_plan(self.album_index)
            self._era_boundary(plan)

            booking = self.book(self.album_index, self.budget.remaining_minutes)
            if booking is None:
                self._log(
                    "cap_reached",
                    album_index=self.album_index,
                    minutes_today=round(self.budget.spent_minutes, 2),
                    cap_minutes=self.config.daily_audio_minutes,
                    generations_today=self.budget.generations_today,
                )
                self._idle(seconds_to_next_utc_day(self.clock()), "heartbeat", waiting="cap")
                continue  # same index; new UTC day, fresh budget

            started = time.monotonic()
            try:
                outcome = self.run_one_album(booking)
                self._consecutive_failures = 0
                self._log(
                    "smoke_completed" if self.smoke else "album_completed",
                    album_index=booking.index,
                    run_id=outcome.run_id,
                    artist=outcome.artist_id,
                    album_id=outcome.album_id,
                    release_id=outcome.release_id,
                    title=outcome.title,
                    minutes_today=round(self.budget.spent_minutes, 2),
                    generations_today=self.budget.generations_today,
                )
            except Exception as err:  # noqa: BLE001 — durability over purity
                self._consecutive_failures += 1
                self._log(
                    "album_failed",
                    album_index=booking.index,
                    run_id=booking.run_id,
                    artist=booking.artist_id,
                    error=f"{type(err).__name__}: {err}"[:500],
                    consecutive_failures=self._consecutive_failures,
                    minutes_today=round(self.budget.spent_minutes, 2),
                    generations_today=self.budget.generations_today,
                )

            if self.smoke or self.rounds_override:
                return 0
            self.album_index += 1
            self._wait(time.monotonic() - started, self.config.albums_per_day)

        self._log("stopped", note="SIGTERM between albums")
        return 0

    def _wait(self, elapsed: float, per_day: float) -> None:
        """Pace to the daily target — or, after a failure, take the short
        backoff instead (a transient outage gets a fast second chance)."""
        if self._consecutive_failures:
            sleep_s = failure_backoff_seconds(
                self._consecutive_failures, self.config.failure_backoff_min, per_day
            )
            self._last_beat = 0.0  # a backoff is an event: its row always lands
            self._idle(
                sleep_s,
                "heartbeat",
                waiting="failure_backoff",
                sleep_seconds=round(sleep_s, 1),
                consecutive_failures=self._consecutive_failures,
            )
        else:
            sleep_s = pace_seconds(elapsed, per_day, self.rng)
            self._idle(sleep_s, "heartbeat", waiting="pace", sleep_seconds=round(sleep_s, 1))

    def _set_loop(self) -> int:
        """EXPERIMENT ONLY (AFAR_EXPERIMENT_MODE=1): the round-based set loop,
        exactly as it ran before the album spine — the offline instrument and
        the code that reproduces releases 0001-0007."""
        while not self._stop:
            plan = self.schedule.set_plan(self.set_index)
            self._era_boundary(plan)

            rounds = self.rounds_override or plan.rounds
            # The gate projects at the 30s floor — "can we afford even the
            # cheapest version of this set?". The Producer's chosen duration
            # is then clamped in _direct so the whole set fits what remains.
            projected_minutes = set_minutes(rounds, len(self.players), 30)
            if self.budget.would_exceed(projected_minutes):
                self._log(
                    "cap_reached",
                    set_index=plan.index,
                    minutes_today=round(self.budget.spent_minutes, 2),
                    projected_minutes=round(projected_minutes, 2),
                    cap_minutes=self.config.daily_audio_minutes,
                    generations_today=self.budget.generations_today,
                )
                self._idle(seconds_to_next_utc_day(self.clock()), "heartbeat", waiting="cap")
                continue  # same set index; new UTC day, fresh budget

            started = time.monotonic()
            try:
                outcome = self.run_one_set(plan)
                self._consecutive_failures = 0
                if not self.smoke:
                    self._log(
                        "set_completed",
                        set_index=plan.index,
                        run_id=outcome.run_id,
                        released=outcome.released,
                        minutes_today=round(self.budget.spent_minutes, 2),
                        generations_today=self.budget.generations_today,
                    )
                else:
                    self._log("smoke_completed", set_index=plan.index, run_id=outcome.run_id,
                              released=outcome.released)
            except SetAborted as err:
                # SIGTERM mid-set: current round finished, checkpoint, exit 0.
                self._log("set_aborted", set_index=plan.index, error=str(err))
                return 0
            except Exception as err:  # noqa: BLE001 — durability over purity
                self._consecutive_failures += 1
                self._log(
                    "set_failed",
                    set_index=plan.index,
                    error=f"{type(err).__name__}: {err}"[:500],
                    consecutive_failures=self._consecutive_failures,
                    minutes_today=round(self.budget.spent_minutes, 2),
                    generations_today=self.budget.generations_today,
                )

            if self.rounds_override or self.smoke:
                # --once/--smoke: exactly one set, then out.
                return 0
            self.set_index += 1
            # A transient failure gets a fast second chance, not the full pace
            # interval (the ElevenLabs-500 lesson); the daily cap check above
            # still governs every attempt's spend.
            self._wait(time.monotonic() - started, self.config.sets_per_day)

        self._log("stopped", note="SIGTERM between sets")
        return 0


# --- wiring -------------------------------------------------------------------


def _build_embedder(config: AfarConfig) -> AudioEmbedder:
    """AFAR_EMBEDDER: mock (default) | mert. The step_b guard, unattended
    edition: a live renderer with mock ears is refused OUTRIGHT — there is no
    override flag on a loop nobody is watching."""
    kind = os.environ.get("AFAR_EMBEDDER", "mock")
    if kind == "mert":
        from afar.perception.embedder import MERTEmbedder

        return MERTEmbedder()
    if kind != "mock":
        raise ValueError(f"AFAR_EMBEDDER must be 'mock' or 'mert', got {kind!r}")
    if config.renderer.name != "mock":
        raise SystemExit(
            "refusing to conduct a live renderer with the mock embedder: audio-space "
            "rows would be placeholder junk (the release 0002 lesson). "
            "Set AFAR_EMBEDDER=mert."
        )
    return MockEmbedder()


def _load_dotenv(path: Path) -> None:
    """Tiny KEY=VALUE loader (same as scripts/step_b.py); real env always wins."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _once_album(conductor: "Conductor", config: AfarConfig, *, smoke: bool) -> int:
    """--once / --smoke on the live spine: book one record, make it, report."""
    conductor._install_signal_handlers()
    booking = conductor.book(conductor.album_index, conductor.budget.remaining_minutes)
    if booking is None:
        print(
            f"daily audio-minutes budget would be exceeded "
            f"({conductor.budget.spent_minutes:.1f}/{config.daily_audio_minutes:.0f} "
            "minutes spent today) — refusing."
        )
        return 1
    conductor._era_boundary(conductor.schedule.set_plan(booking.index))
    outcome = conductor.run_one_album(booking)
    kind = "smoke_completed" if smoke else "album_completed"
    conductor._log(
        kind,
        album_index=booking.index,
        run_id=outcome.run_id,
        artist=outcome.artist_id,
        album_id=outcome.album_id,
        release_id=outcome.release_id,
        title=outcome.title,
    )
    print(
        f"{kind}: album {booking.index} by {outcome.artist_id} "
        f"({booking.size.tracks} x {booking.size.track_seconds}s) "
        f"run_id={outcome.run_id} title={outcome.title!r} publish={outcome.publish}"
    )
    return 0


def _once_set(conductor: "Conductor", config: AfarConfig, *, smoke: bool, rounds_override: Optional[int]) -> int:
    """--once / --smoke on the experiment instrument: one round-based set."""
    conductor._install_signal_handlers()
    plan = conductor.schedule.set_plan(conductor.set_index)
    rounds = rounds_override or plan.rounds
    if conductor.budget.would_exceed(set_minutes(rounds, len(conductor.players), 30)):
        print(
            f"daily audio-minutes budget would be exceeded "
            f"({conductor.budget.spent_minutes:.1f}/{config.daily_audio_minutes:.0f} "
            "minutes spent today) — refusing."
        )
        return 1
    conductor._era_boundary(plan)
    try:
        outcome = conductor.run_one_set(plan)
    except SetAborted as err:
        conductor._log("set_aborted", set_index=plan.index, error=str(err))
        return 0
    kind = "smoke_completed" if smoke else "set_completed"
    conductor._log(kind, set_index=plan.index, run_id=outcome.run_id, released=outcome.released)
    print(
        f"{kind}: set {plan.index} ({outcome.condition}, {rounds} rounds) "
        f"run_id={outcome.run_id} released={outcome.released} publish={outcome.publish}"
    )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AFAR's conductor: the continuous loop.")
    parser.add_argument(
        "--once", action="store_true", help="run exactly one booked album (or set), then exit"
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="supervised smoke: one small record, publish forced DRY-RUN, "
        "cursor not advanced (rows tagged smoke)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="EXPERIMENT MODE ONLY: override rounds per set (with --once/--smoke)",
    )
    args = parser.parse_args(argv)

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if args.smoke:
        # A smoke must never seed the piece: its mock rows (a mock album, a
        # mock reaction, mock audio) would be read by the first REAL booking
        # (album_log / load_recent_reactions scan the whole runs root).
        # Smokes run in a sibling root, canonical runs/ untouched.
        default_root = Path(__file__).resolve().parents[1] / ".." / "runs"
        root = Path(os.environ.get("AFAR_RUNS_ROOT", str(default_root))).resolve()
        os.environ["AFAR_RUNS_ROOT"] = str(root.parent / f"{root.name}-smoke")
    config = build_config()

    if not config.enabled and (args.once or args.smoke):
        print("AFAR_ENABLED != 1 — nothing to run (the master switch is off).")
        return 0

    rounds_override = args.rounds if (args.once or args.smoke) else None
    if args.smoke and rounds_override is None and config.experiment_mode:
        rounds_override = 2

    conductor = Conductor(config, rounds_override=rounds_override, smoke=args.smoke)
    if args.once or args.smoke:
        if config.experiment_mode:
            return _once_set(
                conductor, config, smoke=args.smoke, rounds_override=rounds_override
            )
        return _once_album(conductor, config, smoke=args.smoke)
    return conductor.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
