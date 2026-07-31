"""The conductor: the thin continuous loop that makes AFAR run forever.

    uv run python -m afar.conductor            # the piece (systemd runs this)
    uv run python -m afar.conductor --smoke    # one 2-round set, publish dry-run
    uv run python -m afar.conductor --once     # one scheduled set, then exit

The conductor is deliberately thin: `afar.schedule` already plans every era
and set from the schedule seed alone, `run_set` already plays a set whole,
and `run_staff` already walks the frame. The conductor only WALKS the plan —
per set: the Producer consumes the Muse's newest logged brief
(`ProducerAgent.direct`, set start, frame side — the only door the world
enters through), `run_set` plays the rounds, the staff chain runs at the
boundary (Producer -> Critic -> Muse -> Listener), the release is PUBLISHED
to Neon (afar.publish; forced dry-run under a mock renderer), and then the
loop paces itself to AFAR_SETS_PER_DAY. The boundary rule holds throughout:
`build_context` remains the only perceive path; nothing the conductor
touches reaches a player mid-set.

SPEND CONTROL (hard, by design):

  - AFAR_ENABLED is the master switch and ships "0": the loop idles, writing
    a `disabled` heartbeat row once an hour — an idle conductor is a healthy
    conductor, and the health timer reads exactly those rows.
  - AFAR_DAILY_GEN_CAP is a hard ceiling on generations (rendered takes) per
    UTC day. The counter lives in a state file (runs/conductor/gen_budget.json)
    so restarts cannot reset spend. A set is only started when its WHOLE
    projected spend (rounds x players) fits under the cap; at the cap the
    conductor finishes nothing new and sleeps to the next UTC day.
  - AFAR_SETS_PER_DAY paces the loop: after each set, sleep so that sets/day
    lands near the target, with +/-20% jitter so the piece never metronomes.
  - The ElevenLabs 2-slot concurrency semaphore stays in-process: the
    conductor is a single process (systemd Type=simple, one instance), so a
    process-local semaphore IS the global one. A second kernel writer would
    need the cluster lease DECISIONS.md already flags.

DURABILITY: each set runs under try/except — a failure logs a `set_failed`
row to the conductor ledger, checkpoints, and the loop continues with the
next planned set (the schedule is position-stable; nothing else shifts).
`set_failed` (and the failure backoff) is reserved for `run_set` itself
failing: a completed set is NEVER voided by staff failure. Staff stages
degrade individually inside `run_staff` (afar.staff — the material always
outranks the commentary), the set still publishes, and the conductor logs a
`staff_degraded` row naming which stages went absent.
A failed set does NOT wait out the full pace interval: the next attempt
comes after a short failure backoff (AFAR_FAILURE_BACKOFF_MIN, default 15
minutes, doubling per consecutive failure, capped at the pace interval;
a completed set resets it) — the daily generation cap still governs, since
failed sets spend real generations.
On boot the conductor resumes idempotently from the JSONL cursor: the
highest set index with a `set_completed`/`set_failed` row, plus one.
SIGTERM is honored mid-set via `run_set(after_round=...)`: the current round
finishes, the partial set's rows stay as history (no release record — an
aborted set never finished), the cursor is NOT advanced, and the process
exits 0; the same set replays whole on the next boot.

ERA BOUNDARIES are the only place slow state moves: on the frame between two
eras the FieldTabooMemory rolls over (a hostile era's observed field moves
carry exactly one era) and every player's SelfState is bumped —
`persona_state` rows log each bump, and on boot the conductor rebuilds each
player's version/residue from those rows, so drift survives restarts.
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
from typing import Any, Callable, Mapping, Optional

from ensemble.agent import SelfState

from afar.agents.muse import Brief
from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.agents.producer import ProducerAgent
from afar.config import AfarConfig, build_config
from afar.intent import PLAYER_IDS
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import AudioEmbedder, MockEmbedder
from afar.run import SetAborted, run_set
from afar.schedule import Schedule, ScheduleConfig, SetPlan
from afar.staff import run_staff
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
    generation cap still governs spend on every attempt."""
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


def seconds_to_next_utc_day(now: datetime) -> float:
    """Sleep-to-the-cap horizon: seconds until the next 00:00 UTC."""
    tomorrow = (now.astimezone(timezone.utc) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1.0, (tomorrow - now.astimezone(timezone.utc)).total_seconds())


class GenBudget:
    """The persistent daily generation counter — the hard cap's memory.

    State file (JSON: {"day": "YYYY-MM-DD", "generations": N}) lives under
    runs/conductor/ so restarts cannot reset spend. The day is UTC; a new day
    resets the counter on first read.
    """

    def __init__(
        self,
        state_path: Path,
        cap: int,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.state_path = Path(state_path)
        self.cap = cap
        self.clock = clock

    def _today(self) -> str:
        return self.clock().astimezone(timezone.utc).date().isoformat()

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if state.get("day") != self._today():
            state = {"day": self._today(), "generations": 0}
        return state

    @property
    def spent_today(self) -> int:
        return int(self._load().get("generations", 0))

    def would_exceed(self, generations: int) -> bool:
        """True when spending `generations` more would break the cap."""
        return self.spent_today + generations > self.cap

    def add(self, generations: int) -> int:
        """Record spend (persisted immediately) and return today's total."""
        state = self._load()
        state["generations"] = int(state.get("generations", 0)) + generations
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
        return state["generations"]


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
    released: bool = False
    publish: Optional[Mapping[str, Any]] = None
    error: Optional[str] = None
    staff_degraded: tuple[str, ...] = ()


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
            self.ledger.run_dir / "gen_budget.json", config.daily_gen_cap, clock=clock
        )
        self.players = [Player(PERSONAS[pid], config.model, config.renderer) for pid in PLAYER_IDS]
        self.producer = ProducerAgent(config.model)
        self._restore_persona_state()

        self._stop = False
        self._last_beat = 0.0
        self._consecutive_failures = 0  # in-memory: a restart retries promptly anyway
        rows = self._rows()
        self.set_index = next_set_index(rows)
        self.taboo = FieldTabooMemory(
            stance=self.schedule.set_plan(self.set_index).era_stance
        )

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
        """Rebuild each player's drifted SelfState from logged persona_state
        rows — drift survives restarts because the log is the memory."""
        latest: dict[str, Mapping[str, Any]] = {}
        for row in self._rows() if hasattr(self, "ledger") else []:
            if row.get("kind") == "persona_state" and row.get("player"):
                latest[row["player"]] = row
        for player in self.players:
            pid = player.persona.metadata["player_id"]
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
        """run_set's per-round seam: count the round's spend, report whether a
        stop was requested (True -> finish the current round and abort)."""
        self.budget.add(len(self.players))
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
                daily_gen_cap=self.config.daily_gen_cap,
                generations_today=self.budget.spent_today,
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

    def _direct(self, plan: SetPlan) -> None:
        """Set start, frame side: the Producer consumes the Muse's newest
        logged brief. Cold start (no brief anywhere) is a plain note — the
        first session of a world opens on silence, honestly."""
        brief = load_newest_brief(self.config.runs_root)
        if brief is None:
            self._log(
                "direction",
                set_index=plan.index,
                has_brief=False,
                note="cold start — no brief logged yet; the acts open on silence",
            )
            return
        direction = self.producer.direct(brief)
        self._log("direction", set_index=plan.index, has_brief=True, direction=direction)

    def _era_boundary(self, plan: SetPlan) -> None:
        """The only place slow state moves (schedule law): taboo roll-over and
        persona drift, both logged."""
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
        for player in self.players:
            pid = player.persona.metadata["player_id"]
            player.self_state = player.self_state.bumped(
                residue={
                    **dict(player.self_state.residue),
                    "era": plan.era,
                    "stance": plan.era_stance,
                }
            )
            self._log(
                "persona_state",
                player=pid,
                era=plan.era,
                version=player.self_state.version,
                obsessions=list(player.self_state.obsessions),
                residue=dict(player.self_state.residue),
            )

    def run_one_set(self, plan: SetPlan) -> SetOutcome:
        """Walk one planned set end to end: direct -> play -> staff -> publish."""
        rounds = self.rounds_override or plan.rounds
        prefix = "smoke-" if self.smoke else ""
        run_id = (
            time.strftime("%Y%m%d-%H%M%S")
            + f"-{prefix}set-{plan.index:04d}-{plan.condition}"
        )
        self._log(
            "set_started",
            set_index=plan.index,
            run_id=run_id,
            era=plan.era,
            stance=plan.era_stance,
            condition=plan.condition,
            rounds=rounds,
            seed=plan.seed,
            renderer=self.config.renderer.name,
            embedder=self.embedder.name,
            generations_today=self.budget.spent_today,
        )
        # Set start, frame side: the brief is consumed HERE and only here.
        self._direct(plan)

        set_ledger = JsonlLedger(
            self.config.runs_root, run_id, context=RunContext(code_sha=self.config.code_sha)
        )
        run_set(
            self.players,
            rounds=rounds,
            condition=plan.condition,
            config=self.config,
            ledger=set_ledger,
            embedder=self.embedder,
            seed=plan.seed,
            after_round=self._after_round,
        )

        # The frame: Producer -> Critic -> Muse -> Listener (existing machinery).
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
        return SetOutcome(
            set_index=plan.index,
            run_id=run_id,
            completed=True,
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
        self._log("published", run_id=run_dir.name, **row)
        return row

    # -- the loop --------------------------------------------------------------

    def run_forever(self) -> int:
        """Iterate the schedule's eras and sets until stopped. Returns the
        process exit code (always 0 — SIGTERM is a clean exit)."""
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
            resume_set_index=self.set_index,
            renderer=self.config.renderer.name,
            embedder=self.embedder.name,
            live_model=self.config.live,
        )

        while not self._stop:
            plan = self.schedule.set_plan(self.set_index)
            self._era_boundary(plan)

            rounds = self.rounds_override or plan.rounds
            projected = rounds * len(self.players)
            if self.budget.would_exceed(projected):
                self._log(
                    "cap_reached",
                    set_index=plan.index,
                    generations_today=self.budget.spent_today,
                    projected=projected,
                    cap=self.config.daily_gen_cap,
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
                        generations_today=self.budget.spent_today,
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
                    generations_today=self.budget.spent_today,
                )

            if self.rounds_override or self.smoke:
                # --once/--smoke: exactly one set, then out.
                return 0
            self.set_index += 1
            elapsed = time.monotonic() - started
            if self._consecutive_failures:
                # A transient failure gets a fast second chance, not the full
                # pace interval (the ElevenLabs-500 lesson). Doubling per
                # consecutive failure, capped at the pace interval; the daily
                # cap check above still governs every attempt's spend.
                sleep_s = failure_backoff_seconds(
                    self._consecutive_failures,
                    self.config.failure_backoff_min,
                    self.config.sets_per_day,
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
                sleep_s = pace_seconds(elapsed, self.config.sets_per_day, self.rng)
                self._idle(sleep_s, "heartbeat", waiting="pace", sleep_seconds=round(sleep_s, 1))

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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AFAR's conductor: the continuous loop.")
    parser.add_argument(
        "--once", action="store_true", help="run exactly one scheduled set, then exit"
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="supervised smoke: one set, rounds default 2, publish forced DRY-RUN, "
        "cursor not advanced (rows tagged smoke)",
    )
    parser.add_argument(
        "--rounds", type=int, default=None, help="override rounds per set (with --once/--smoke)"
    )
    args = parser.parse_args(argv)

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if args.smoke:
        # A smoke must never seed the piece: its mock rows (a mock brief, a
        # mock reaction, mock audio) would be read by the first REAL boundary
        # (load_newest_brief / load_recent_reactions scan the whole runs
        # root). Smokes run in a sibling root, canonical runs/ untouched.
        default_root = Path(__file__).resolve().parents[1] / ".." / "runs"
        root = Path(os.environ.get("AFAR_RUNS_ROOT", str(default_root))).resolve()
        os.environ["AFAR_RUNS_ROOT"] = str(root.parent / f"{root.name}-smoke")
    config = build_config()

    if not config.enabled and (args.once or args.smoke):
        print("AFAR_ENABLED != 1 — nothing to run (the master switch is off).")
        return 0

    rounds_override = args.rounds if (args.once or args.smoke) else None
    if args.smoke and rounds_override is None:
        rounds_override = 2

    conductor = Conductor(config, rounds_override=rounds_override, smoke=args.smoke)
    if args.once or args.smoke:
        conductor._install_signal_handlers()
        plan = conductor.schedule.set_plan(conductor.set_index)
        rounds = rounds_override or plan.rounds
        if conductor.budget.would_exceed(rounds * len(conductor.players)):
            print(
                f"daily generation cap would be exceeded "
                f"({conductor.budget.spent_today}/{config.daily_gen_cap} spent today) — refusing."
            )
            return 1
        conductor._era_boundary(plan)
        try:
            outcome = conductor.run_one_set(plan)
        except SetAborted as err:
            conductor._log("set_aborted", set_index=plan.index, error=str(err))
            return 0
        kind = "smoke_completed" if args.smoke else "set_completed"
        conductor._log(kind, set_index=plan.index, run_id=outcome.run_id, released=outcome.released)
        print(
            f"{kind}: set {plan.index} ({plan.condition}, "
            f"{rounds_override or plan.rounds} rounds) run_id={outcome.run_id} "
            f"released={outcome.released} publish={outcome.publish}"
        )
        return 0
    return conductor.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
