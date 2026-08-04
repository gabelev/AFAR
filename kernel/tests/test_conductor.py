"""The conductor: pacing math, the daily cap, the cursor, and one walked set.

Everything offline (MockProvider + MockRenderer + MockEmbedder). The pacing
and budget arithmetic is pure and tested as such; the end-to-end test walks
ONE smoke set through the full chain — direct, run_set, staff, publish
DRY-RUN — exactly what the droplet smoke does.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest
from ensemble.providers.model import MockProvider

from afar.config import AfarConfig, _mock_players
from afar.conductor import (
    Conductor,
    GenBudget,
    SECONDS_PER_DAY,
    SetOutcome,
    failure_backoff_seconds,
    load_newest_brief,
    next_set_index,
    pace_seconds,
    seconds_to_next_utc_day,
)
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.run import SetAborted


def _config(
    root: Path,
    *,
    enabled: bool = True,
    minutes: float = 110.0,
    experiment_mode: bool = False,
) -> AfarConfig:
    return AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=MockRenderer(root / "audio"),
        runs_root=root,
        live=False,
        code_sha="test-sha",
        enabled=enabled,
        sets_per_day=3.0,
        asks_per_day=8.0,
        daily_audio_minutes=minutes,
        experiment_mode=experiment_mode,
    )


def _conductor(root: Path, **kw) -> Conductor:
    kw.setdefault("embedder", MockEmbedder())
    config = kw.pop("config", None) or _config(root, **{
        k: kw.pop(k) for k in ("enabled", "minutes", "experiment_mode") if k in kw
    })
    return Conductor(config, **kw)


def _conductor_rows(root: Path) -> list[dict]:
    path = root / "conductor" / "conductor.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- pacing (pure) ------------------------------------------------------------


def test_pace_targets_sets_per_day_with_bounded_jitter():
    rng = random.Random(0)
    base = SECONDS_PER_DAY / 3.0
    for _ in range(200):
        s = pace_seconds(0.0, 3.0, rng)
        assert base * 0.8 <= s <= base * 1.2


def test_pace_subtracts_the_sets_own_elapsed_time():
    class FixedRng:
        def uniform(self, a, b):
            return 1.0  # no jitter

    assert pace_seconds(1000.0, 3.0, FixedRng()) == SECONDS_PER_DAY / 3.0 - 1000.0


def test_pace_never_goes_negative_and_rejects_bad_rates():
    class FixedRng:
        def uniform(self, a, b):
            return 0.8

    assert pace_seconds(10 * SECONDS_PER_DAY, 3.0, FixedRng()) == 0.0
    with pytest.raises(ValueError):
        pace_seconds(0.0, 0.0, random.Random(0))


def test_seconds_to_next_utc_day():
    now = datetime(2026, 7, 31, 23, 0, 0, tzinfo=timezone.utc)
    assert seconds_to_next_utc_day(now) == 3600.0


# --- the failure backoff (pure) -----------------------------------------------


def test_failure_backoff_doubles_per_consecutive_failure_and_caps_at_the_pace():
    pace = SECONDS_PER_DAY / 3.0  # 28800s at 3 sets/day
    assert failure_backoff_seconds(1, 15.0, 3.0) == 900.0  # 15 min
    assert failure_backoff_seconds(2, 15.0, 3.0) == 1800.0  # 30 min
    assert failure_backoff_seconds(3, 15.0, 3.0) == 3600.0  # 60 min
    assert failure_backoff_seconds(6, 15.0, 3.0) == pace  # 900 * 2^5 hits the cap exactly
    assert failure_backoff_seconds(50, 15.0, 3.0) == pace  # never past normal pacing
    assert failure_backoff_seconds(1, 30.0, 3.0) == 1800.0  # the knob is minutes


def test_failure_backoff_rejects_bad_inputs():
    with pytest.raises(ValueError):
        failure_backoff_seconds(0, 15.0, 3.0)
    with pytest.raises(ValueError):
        failure_backoff_seconds(1, 15.0, 0.0)


def test_failure_backoff_min_env_knob(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from afar.config import build_config

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AFAR_FAILURE_BACKOFF_MIN", raising=False)
    monkeypatch.setenv("AFAR_RUNS_ROOT", str(tmp_path))
    assert build_config().failure_backoff_min == 15.0
    monkeypatch.setenv("AFAR_FAILURE_BACKOFF_MIN", "5")
    assert build_config().failure_backoff_min == 5.0
    monkeypatch.setenv("AFAR_FAILURE_BACKOFF_MIN", "0")
    with pytest.raises(ValueError):
        build_config()


def test_set_failure_gets_a_fast_retry_and_success_resets_the_backoff(tmp_path: Path):
    """The droplet lesson: a set that died on a transient 500 must not wait
    the full ~8h pace interval for its next attempt — 15 min, doubling per
    consecutive failure, and one completed set resets the schedule."""
    # The round-based instrument's loop — the backoff is shared, and the
    # album loop's own version of this test lives in test_album_loop.py.
    conductor = _conductor(tmp_path, experiment_mode=True)
    outcomes = iter(["fail", "fail", "ok"])

    def fake_run_one_set(plan):
        if next(outcomes) == "fail":
            raise RuntimeError("ElevenLabs music request failed (500): service_unavailable")
        return SetOutcome(set_index=plan.index, run_id=f"run-{plan.index}", completed=True)

    idles: list[tuple[float, dict]] = []

    def fake_idle(seconds: float, kind: str, **row) -> None:
        idles.append((seconds, row))
        if len(idles) >= 3:
            conductor._stop = True

    conductor.run_one_set = fake_run_one_set
    conductor._idle = fake_idle
    assert conductor.run_forever() == 0

    # Failure 1 -> 15 min, failure 2 -> 30 min, success -> normal pacing again;
    # the chosen sleep rides in the heartbeat/pacing row.
    assert idles[0][0] == 900.0
    assert idles[0][1]["waiting"] == "failure_backoff"
    assert idles[0][1] == {"waiting": "failure_backoff", "sleep_seconds": 900.0,
                           "consecutive_failures": 1}
    assert idles[1][0] == 1800.0
    assert idles[1][1]["consecutive_failures"] == 2
    assert idles[2][1]["waiting"] == "pace"
    assert idles[2][1]["sleep_seconds"] == round(idles[2][0], 1)
    assert conductor._consecutive_failures == 0

    rows = _conductor_rows(tmp_path)
    assert [r["consecutive_failures"] for r in rows if r["kind"] == "set_failed"] == [1, 2]
    assert len([r for r in rows if r["kind"] == "set_completed"]) == 1
    assert conductor.set_index == 3  # failed sets still advance the cursor


# --- the cursor (pure) --------------------------------------------------------


def test_cursor_starts_at_zero_and_resumes_past_completed_and_failed():
    assert next_set_index([]) == 0
    rows = [
        {"kind": "set_completed", "set_index": 0},
        {"kind": "set_failed", "set_index": 1},
        {"kind": "heartbeat"},
    ]
    assert next_set_index(rows) == 2


def test_cursor_ignores_aborted_and_smoke_rows():
    rows = [
        {"kind": "set_completed", "set_index": 3},
        {"kind": "set_aborted", "set_index": 4},  # SIGTERM: replays whole
        {"kind": "smoke_completed", "set_index": 9},  # smoke never advances
    ]
    assert next_set_index(rows) == 4


# --- the budget (persistent, minutes-based) -----------------------------------


def test_gen_budget_persists_across_instances(tmp_path: Path):
    path = tmp_path / "gen_budget.json"
    one = GenBudget(path, minutes_cap=10.0)
    assert one.spent_minutes == 0.0
    assert one.generations_today == 0
    one.add(generations=6, minutes=6.0)
    two = GenBudget(path, minutes_cap=10.0)  # a restart
    assert two.spent_minutes == 6.0
    assert two.generations_today == 6
    assert two.remaining_minutes == 4.0
    assert not two.would_exceed(4.0)
    assert two.would_exceed(4.5)


def test_gen_budget_resets_on_the_next_utc_day(tmp_path: Path):
    path = tmp_path / "gen_budget.json"
    day = [datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)]
    budget = GenBudget(path, minutes_cap=10.0, clock=lambda: day[0])
    budget.add(generations=18, minutes=9.0)
    assert budget.would_exceed(3.0)
    day[0] = datetime(2026, 8, 1, 0, 1, tzinfo=timezone.utc)
    assert budget.spent_minutes == 0.0
    assert budget.generations_today == 0
    assert not budget.would_exceed(3.0)


def test_gen_budget_migrates_the_old_generations_only_state_file(tmp_path: Path):
    """The generation-cap era's {day, generations} file: the count is kept as
    telemetry and minutes are estimated at 0.5/generation (every old take
    was 30s) — a deploy mid-day never resets or double-counts spend."""
    path = tmp_path / "gen_budget.json"
    day = [datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)]
    path.write_text(json.dumps({"day": "2026-07-31", "generations": 40}) + "\n")
    budget = GenBudget(path, minutes_cap=110.0, clock=lambda: day[0])
    assert budget.spent_minutes == 20.0  # 40 x 0.5
    assert budget.generations_today == 40
    budget.add(generations=3, minutes=1.5)
    state = json.loads(path.read_text())
    assert state["minutes"] == 21.5
    assert state["generations"] == 43


def test_set_minutes_and_fit_duration():
    from afar.conductor import fit_duration_s, set_minutes

    # 10 rounds x 3 players x 60s = 30 audio-minutes.
    assert set_minutes(10, 3, 60) == 30.0
    assert set_minutes(2, 3, 30) == 3.0
    # The Producer wanted 120s but only 30 minutes remain for a 10x3 set:
    # 30 min = 1800s across 30 takes -> 60s each.
    assert fit_duration_s(120, 10, 3, 30.0) == 60
    # Plenty of budget: the choice stands.
    assert fit_duration_s(90, 2, 3, 100.0) == 90
    # Never below the 30s floor (the pre-set gate owns refusing outright).
    assert fit_duration_s(120, 10, 3, 1.0) == 30


def test_top_obsessions_ranks_recurrence_then_first_seen():
    from afar.conductor import top_obsessions

    tags = [
        ["sediment", "rooms filling"],
        ["Sediment", "the flood"],  # case-insensitive fold; first casing wins
        ["the flood", "rooms filling", "sediment"],
        ["one-off"],
    ]
    assert top_obsessions(tags) == ["sediment", "rooms filling", "the flood"]
    assert top_obsessions([]) == []
    assert top_obsessions(tags, limit=1) == ["sediment"]


# --- the newest brief ---------------------------------------------------------


def test_load_newest_brief_none_on_cold_start(tmp_path: Path):
    assert load_newest_brief(tmp_path) is None


def test_load_newest_brief_reads_the_latest_row_across_runs(tmp_path: Path):
    older = JsonlLedger(tmp_path, "run-a", context=RunContext())
    older.write("briefs", {"kind": "brief", "ts": "2026-07-30T00:00:00+00:00",
                           "stance": "porous", "theme": "old", "text": "old brief",
                           "palette_notes": [], "forbidden_moves": [], "sources": []})
    newer = JsonlLedger(tmp_path, "run-b", context=RunContext())
    newer.write("briefs", {"kind": "brief", "stance": "hostile", "theme": "rooms",
                           "text": "reach for the seam", "palette_notes": ["close"],
                           "forbidden_moves": ["field-move x"], "sources": ["https://x"],
                           "thin": False, "carried_forward": True})
    brief = load_newest_brief(tmp_path)
    assert brief is not None
    assert brief.theme == "rooms"
    assert brief.body == "reach for the seam"
    assert brief.carried_forward is True
    assert brief.palette_notes == ("close",)


# --- one walked set, end to end (the droplet smoke, offline) ------------------


def test_smoke_set_walks_the_full_chain_with_dry_run_publish(tmp_path: Path):
    conductor = _conductor(tmp_path, rounds_override=2, smoke=True)
    plan = conductor.schedule.set_plan(0)
    outcome = conductor.run_one_set(plan)

    assert outcome.completed and outcome.released
    run_dir = tmp_path / outcome.run_id
    # Live mode, cold start (no brief anywhere): the session defaults to
    # "together" — the schedule's drawn condition does not book the room.
    assert outcome.condition == "contact"
    assert outcome.run_id.endswith("-smoke-set-0000-contact")

    # The set itself: rounds played, release records chained by the staff.
    assert len((run_dir / "rounds.jsonl").read_text().splitlines()) == 2
    for table in ("selections", "reviews", "briefs", "reactions"):
        assert (run_dir / f"{table}.jsonl").exists(), f"staff never wrote {table}"

    # The publish was DRY: logged with real byte counts, nothing external.
    published = [r for r in _conductor_rows(tmp_path) if r["kind"] == "published"]
    assert len(published) == 1
    assert published[0]["dry_run"] is True
    assert published[0]["smoke"] is True
    assert set(published[0]["media_bytes"]) == {"silt", "rust", "keep"}
    assert all(count >= 1000 for count in published[0]["media_bytes"].values())
    assert published[0]["timeline_blocks"] == 1

    # The spend was metered and persisted: 2 rounds x 3 players x 30s = 3 min,
    # with the generation count riding along as telemetry.
    assert conductor.budget.spent_minutes == 3.0
    assert conductor.budget.generations_today == 6

    # The direction ran at set start (cold start: no brief yet -> plain note).
    (direction,) = [r for r in _conductor_rows(tmp_path) if r["kind"] == "direction"]
    assert direction["has_brief"] is False


def test_staff_failure_degrades_and_still_publishes_never_set_failed(tmp_path: Path):
    """The stranded-set doctrine: run_set success + staff failure => per-stage
    degradation and a published release — `set_failed` (and its backoff) is
    reserved for run_set itself failing."""

    def critic_dead(messages):
        text = "\n".join(m.content for m in messages)
        if "The set is finished and cut. Review it." in text or "Name it — the last word." in text:
            return ""  # the observed failure mode: an empty staff reply, every time
        return _mock_players(messages)

    config = AfarConfig(
        model=MockProvider(responder=critic_dead),
        renderer=MockRenderer(tmp_path / "audio"),
        runs_root=tmp_path,
        live=False,
        code_sha="test-sha",
        enabled=True,
        sets_per_day=3.0,
        daily_audio_minutes=110.0,
    )
    conductor = _conductor(tmp_path, config=config, rounds_override=2, smoke=True)
    outcome = conductor.run_one_set(conductor.schedule.set_plan(0))

    assert outcome.completed and outcome.released
    assert outcome.staff_degraded == ("critic",)
    rows = _conductor_rows(tmp_path)
    (degraded_row,) = [r for r in rows if r["kind"] == "staff_degraded"]
    assert degraded_row["stages"] == ["critic"]
    assert degraded_row["run_id"] == outcome.run_id
    assert not [r for r in rows if r["kind"] == "set_failed"]
    # The release still published (dry — smoke), title honestly placeholdered.
    (published,) = [r for r in rows if r["kind"] == "published"]
    assert published["release_title"].startswith("Untitled Session")
    assert published["dry_run"] is True


def test_direction_consumes_the_newest_logged_brief(tmp_path: Path):
    ledger = JsonlLedger(tmp_path, "prior-run", context=RunContext())
    ledger.write("briefs", {"kind": "brief", "stance": "porous", "theme": "rooms",
                            "text": "reach", "palette_notes": [], "forbidden_moves": [],
                            "sources": [], "thin": False, "carried_forward": True})
    conductor = _conductor(tmp_path, rounds_override=2, smoke=True)
    returned = conductor._direct(conductor.schedule.set_plan(0), rounds=2)
    (direction,) = [r for r in _conductor_rows(tmp_path) if r["kind"] == "direction"]
    assert direction["has_brief"] is True
    assert direction["direction"]["theme"] == "rooms"
    # The Producer set the take length (mock chooses the 30s sketch) and the
    # same direction is what run_set will receive.
    assert direction["direction"]["duration_s"] == 30
    assert returned == direction["direction"]


# --- sessions, not conditions: the office books the room ------------------------


def _log_brief(root: Path, run: str = "prior-run") -> None:
    ledger = JsonlLedger(root, run, context=RunContext())
    ledger.write("briefs", {"kind": "brief", "stance": "porous", "theme": "rooms",
                            "text": "reach for the seam", "palette_notes": [],
                            "forbidden_moves": [], "sources": [], "thin": False,
                            "carried_forward": True})


def _run_row(root: Path, run_id: str) -> dict:
    (row,) = [json.loads(line)
              for line in (root / run_id / "runs.jsonl").read_text().splitlines()]
    return row


def test_live_mode_books_the_session_from_the_producer(tmp_path: Path):
    """The default (no experiment flag): the Producer's session_form — not the
    schedule's draw — is the condition run_set receives, and the booking's
    reasoning rides in the direction row."""
    _log_brief(tmp_path)
    conductor = _conductor(tmp_path, rounds_override=2, smoke=True)
    outcome = conductor.run_one_set(conductor.schedule.set_plan(0))

    assert outcome.condition == "contact"  # the mock Producer books "together"
    assert outcome.run_id.endswith("-contact")
    rows = _conductor_rows(tmp_path)
    (started,) = [r for r in rows if r["kind"] == "set_started"]
    assert started["condition"] == "contact"
    assert started["session_form"] == "together"
    assert started["booked_by"] == "producer"
    (direction,) = [r for r in rows if r["kind"] == "direction"]
    assert direction["direction"]["session_form"] == "together"
    assert direction["direction"]["session_why"]
    # And run_set actually played the booked condition.
    assert _run_row(tmp_path, outcome.run_id)["condition"] == "contact"


def test_live_mode_books_alone_when_the_producer_says_so(tmp_path: Path):
    _log_brief(tmp_path)

    def alone_booker(messages):
        text = "\n".join(m.content for m in messages)
        if '"session_form"' in text and "book the room" in text:
            return json.dumps({"session_form": "alone",
                               "why": "a hostile week wants the doors closed"})
        return _mock_players(messages)

    config = _config(tmp_path)
    config.model = MockProvider(responder=alone_booker)
    conductor = _conductor(tmp_path, config=config, rounds_override=2, smoke=True)
    outcome = conductor.run_one_set(conductor.schedule.set_plan(0))

    assert outcome.condition == "isolation"
    assert outcome.run_id.endswith("-isolation")
    (started,) = [r for r in _conductor_rows(tmp_path) if r["kind"] == "set_started"]
    assert started["session_form"] == "alone" and started["booked_by"] == "producer"
    assert _run_row(tmp_path, outcome.run_id)["condition"] == "isolation"


def test_live_booking_degrades_to_together_and_the_direction_still_ships(tmp_path: Path):
    """The staff-degrade doctrine: an unusable booking call defaults the
    session to "together" — the set still runs, directed."""
    _log_brief(tmp_path)

    def booking_dead(messages):
        text = "\n".join(m.content for m in messages)
        if '"session_form"' in text and "book the room" in text:
            return "not json at all"
        return _mock_players(messages)

    config = _config(tmp_path)
    config.model = MockProvider(responder=booking_dead)
    conductor = _conductor(tmp_path, config=config, rounds_override=2, smoke=True)
    outcome = conductor.run_one_set(conductor.schedule.set_plan(0))

    assert outcome.completed and outcome.condition == "contact"
    (direction,) = [r for r in _conductor_rows(tmp_path) if r["kind"] == "direction"]
    assert direction["direction"]["session_form"] == "together"
    assert "did not file" in direction["direction"]["session_why"]
    assert direction["direction"]["theme"] == "rooms"  # the direction shipped whole


def test_experiment_mode_runs_the_schedules_draw_parallel_included(tmp_path: Path):
    """AFAR_EXPERIMENT_MODE: the old scheduled behavior exactly — the
    deterministic condition draw (parallel included) books every set and the
    Producer books nothing (the direction is the pre-booking shape)."""
    from afar.schedule import Schedule, ScheduleConfig

    _log_brief(tmp_path)
    config = _config(tmp_path)
    config.experiment_mode = True
    conductor = _conductor(
        tmp_path, config=config, rounds_override=2, smoke=True,
        schedule=Schedule(ScheduleConfig(condition_bias=(0, 0, 1))),
    )
    plan = conductor.schedule.set_plan(0)
    assert plan.condition == "parallel"
    outcome = conductor.run_one_set(plan)

    assert outcome.condition == "parallel"
    assert outcome.run_id.endswith("-parallel")
    rows = _conductor_rows(tmp_path)
    (started,) = [r for r in rows if r["kind"] == "set_started"]
    assert started["booked_by"] == "schedule"
    (direction,) = [r for r in rows if r["kind"] == "direction"]
    assert "session_form" not in direction["direction"]
    assert _run_row(tmp_path, outcome.run_id)["condition"] == "parallel"


def test_live_mode_can_never_book_parallel():
    """The booking vocabulary is exactly together/alone: parallel is a lab
    condition, structurally unreachable from the live path (a model reply
    asking for it fails parsing and degrades to together — test_seams)."""
    from afar.agents.producer import SESSION_FORM_CONDITIONS, SESSION_FORMS

    assert SESSION_FORMS == ("together", "alone")
    assert set(SESSION_FORM_CONDITIONS.values()) == {"contact", "isolation"}


def test_the_booking_is_informed_by_the_fan_and_the_recent_forms(tmp_path: Path):
    """What governs the call: the brief, the Listener's last word, and the
    last few sessions' forms all reach the booking prompt."""
    _log_brief(tmp_path)
    JsonlLedger(tmp_path, "prior-run", context=RunContext()).write(
        "reactions", {"kind": "reaction", "valence": "liked",
                      "text": "the quiet one got me", "ts": "2026-07-30T00:00:00+00:00"})
    history = JsonlLedger(tmp_path, "conductor", context=RunContext())
    history.write("conductor", {"kind": "set_started", "set_index": 0, "condition": "contact"})
    history.write("conductor", {"kind": "set_started", "set_index": 1, "condition": "isolation"})

    prompts: list[str] = []

    def capturing(messages):
        text = "\n".join(m.content for m in messages)
        if '"session_form"' in text and "book the room" in text:
            prompts.append(text)
        return _mock_players(messages)

    config = _config(tmp_path)
    config.model = MockProvider(responder=capturing)
    conductor = _conductor(tmp_path, config=config, rounds_override=2, smoke=True)
    conductor._direct(conductor.schedule.set_plan(0), rounds=2)

    (prompt,) = prompts
    assert "the quiet one got me" in prompt
    assert "together, alone" in prompt  # oldest first
    assert "reach for the seam" in prompt  # the brief itself


def test_recent_session_forms_reads_oldest_first_and_skips_smoke():
    from afar.conductor import recent_session_forms

    rows = [
        {"kind": "set_started", "condition": "contact"},
        {"kind": "set_started", "condition": "parallel"},
        {"kind": "set_started", "condition": "isolation", "smoke": True},
        {"kind": "heartbeat"},
        {"kind": "set_started", "condition": "isolation"},
    ]
    assert recent_session_forms(rows) == [
        "together", "side by side, unable to hear each other", "alone"]
    assert recent_session_forms(rows, limit=1) == ["alone"]
    assert recent_session_forms([]) == []


def test_experiment_mode_env_knob(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from afar.config import build_config

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AFAR_RUNS_ROOT", str(tmp_path))
    monkeypatch.delenv("AFAR_EXPERIMENT_MODE", raising=False)
    assert build_config().experiment_mode is False
    monkeypatch.setenv("AFAR_EXPERIMENT_MODE", "1")
    assert build_config().experiment_mode is True
    monkeypatch.setenv("AFAR_EXPERIMENT_MODE", "0")
    assert build_config().experiment_mode is False


def test_sigterm_mid_set_finishes_the_round_and_aborts(tmp_path: Path):
    conductor = _conductor(tmp_path, rounds_override=3, smoke=True)
    conductor._stop = True  # SIGTERM already requested
    with pytest.raises(SetAborted):
        conductor.run_one_set(conductor.schedule.set_plan(0))
    run_dirs = [p for p in tmp_path.iterdir() if "smoke-set-" in p.name]
    assert len(run_dirs) == 1
    # Exactly one full round was logged, and NO release record was written.
    assert len((run_dirs[0] / "rounds.jsonl").read_text().splitlines()) == 1
    assert not list(run_dirs[0].glob("release-*.json"))
    # The finished round's spend was still metered: 3 takes x 30s = 1.5 min.
    assert conductor.budget.spent_minutes == 1.5
    assert conductor.budget.generations_today == 3


def test_disabled_conductor_idles_and_heartbeats(tmp_path: Path):
    conductor = _conductor(tmp_path, enabled=False)
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            conductor._stop = True

    conductor._sleep = fake_sleep
    assert conductor.run_forever() == 0
    rows = _conductor_rows(tmp_path)
    assert [r["kind"] for r in rows if r["kind"] == "disabled"], "no disabled heartbeat"
    disabled = [r for r in rows if r["kind"] == "disabled"]
    assert disabled[0]["enabled"] is False
    assert rows[-1]["kind"] == "stopped"


def test_resume_reads_the_cursor_and_persona_state(tmp_path: Path):
    ledger = JsonlLedger(tmp_path, "conductor", context=RunContext())
    ledger.write("conductor", {"kind": "set_completed", "set_index": 0, "run_id": "x"})
    ledger.write("conductor", {"kind": "set_failed", "set_index": 1, "error": "boom"})
    ledger.write("conductor", {"kind": "persona_state", "player": "silt", "version": 2,
                               "obsessions": [], "residue": {"era": 1, "stance": "hostile"}})
    conductor = _conductor(tmp_path)
    assert conductor.set_index == 2
    silt = next(p for p in conductor.players if p.persona.metadata["player_id"] == "silt")
    assert silt.self_state.version == 2
    assert silt.self_state.residue["stance"] == "hostile"


def test_era_boundary_rolls_taboo_and_bumps_personas(tmp_path: Path):
    from afar.schedule import Schedule, ScheduleConfig

    conductor = _conductor(tmp_path, schedule=Schedule(ScheduleConfig(sets_per_era=1)))
    plan = conductor.schedule.set_plan(1)  # set 1 opens era 1 -> a boundary
    assert conductor.schedule.should_roll_taboo(1)
    conductor._era_boundary(plan)

    eras_path = tmp_path / "conductor" / "eras.jsonl"
    (era_row,) = [json.loads(line) for line in eras_path.read_text().splitlines()]
    assert era_row["kind"] == "era_open" and era_row["era"] == 1
    persona_rows = [r for r in _conductor_rows(tmp_path) if r["kind"] == "persona_state"]
    # The album loop books the WHOLE roster, so the whole roster drifts.
    bumped = {r["player"] for r in persona_rows}
    assert bumped == set(conductor.roster) and {"silt", "rust", "keep"} <= bumped
    assert all(r["version"] == 1 for r in persona_rows)
    for player in conductor.players:
        assert player.self_state.version == 1
        assert player.self_state.residue["era"] == 1


def test_cap_reached_blocks_the_set(tmp_path: Path):
    from afar.conductor import set_minutes

    conductor = _conductor(tmp_path, minutes=2.5, rounds_override=2, smoke=True)
    # Even the cheapest projection (2 rounds x 3 players x 30s = 3 min)
    # overruns a 2.5-minute day.
    assert conductor.budget.would_exceed(set_minutes(2, len(conductor.players), 30))


def test_smoke_cli_runs_in_a_sibling_root_never_the_canonical_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """--smoke must not seed the piece: the real Muse reads briefs/reactions
    across the whole runs root, so smokes get a runs-smoke sibling."""
    from afar.conductor import main

    canonical = tmp_path / "runs"
    canonical.mkdir()
    monkeypatch.setenv("AFAR_RUNS_ROOT", str(canonical))
    monkeypatch.setenv("AFAR_ENABLED", "1")
    monkeypatch.setenv("AFAR_RENDERER", "mock")
    monkeypatch.setenv("AFAR_EMBEDDER", "mock")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # force the mock model

    assert main(["--smoke"]) == 0
    assert not any(canonical.iterdir()), "smoke wrote into the canonical runs root"
    smoke_root = tmp_path / "runs-smoke"
    assert (smoke_root / "conductor" / "conductor.jsonl").exists()
    assert any(p.name.startswith("2") and "smoke-album-" in p.name for p in smoke_root.iterdir())


# --- publish preflight: never spend before the record has somewhere to land ---


def test_preflight_is_silent_for_a_mock_renderer(tmp_path) -> None:
    """Mock runs publish dry, so they need no driver and no database."""
    from afar.publish import publish_preflight

    class _Cfg:
        renderer = type("R", (), {"name": "mock"})()

    assert publish_preflight(_Cfg()) == []


def test_preflight_names_a_missing_driver_for_a_live_renderer(monkeypatch) -> None:
    """AFAR-0008 rendered four paid tracks before psycopg turned up missing."""
    import builtins

    from afar.publish import publish_preflight

    class _Cfg:
        renderer = type("R", (), {"name": "elevenlabs"})()

    real_import = builtins.__import__

    def _no_psycopg(name, *args, **kw):
        if name == "psycopg":
            raise ImportError("no psycopg")
        return real_import(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_psycopg)
    reasons = publish_preflight(_Cfg())
    assert any("psycopg" in r for r in reasons)
    assert any("--extra publish" in r for r in reasons)


def test_preflight_names_a_missing_database_url(monkeypatch) -> None:
    from afar import publish as publish_mod

    class _Cfg:
        renderer = type("R", (), {"name": "elevenlabs"})()

    monkeypatch.setattr(publish_mod, "load_database_url", lambda *a, **kw: None)
    assert any("DATABASE_URL" in r for r in publish_mod.publish_preflight(_Cfg()))
