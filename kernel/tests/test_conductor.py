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
    load_newest_brief,
    next_set_index,
    pace_seconds,
    seconds_to_next_utc_day,
)
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.run import SetAborted


def _config(root: Path, *, enabled: bool = True, cap: int = 60) -> AfarConfig:
    return AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=MockRenderer(root / "audio"),
        runs_root=root,
        live=False,
        code_sha="test-sha",
        enabled=enabled,
        sets_per_day=3.0,
        daily_gen_cap=cap,
    )


def _conductor(root: Path, **kw) -> Conductor:
    kw.setdefault("embedder", MockEmbedder())
    config = kw.pop("config", None) or _config(root, **{
        k: kw.pop(k) for k in ("enabled", "cap") if k in kw
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


# --- the budget (persistent) --------------------------------------------------


def test_gen_budget_persists_across_instances(tmp_path: Path):
    path = tmp_path / "gen_budget.json"
    one = GenBudget(path, cap=10)
    assert one.spent_today == 0
    one.add(6)
    two = GenBudget(path, cap=10)  # a restart
    assert two.spent_today == 6
    assert not two.would_exceed(4)
    assert two.would_exceed(5)


def test_gen_budget_resets_on_the_next_utc_day(tmp_path: Path):
    path = tmp_path / "gen_budget.json"
    day = [datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)]
    budget = GenBudget(path, cap=10, clock=lambda: day[0])
    budget.add(9)
    assert budget.would_exceed(3)
    day[0] = datetime(2026, 8, 1, 0, 1, tzinfo=timezone.utc)
    assert budget.spent_today == 0
    assert not budget.would_exceed(3)


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
    assert outcome.run_id.endswith(f"-smoke-set-0000-{plan.condition}")

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

    # The spend was counted and persisted: 2 rounds x 3 players.
    assert conductor.budget.spent_today == 6

    # The direction ran at set start (cold start: no brief yet -> plain note).
    (direction,) = [r for r in _conductor_rows(tmp_path) if r["kind"] == "direction"]
    assert direction["has_brief"] is False


def test_direction_consumes_the_newest_logged_brief(tmp_path: Path):
    ledger = JsonlLedger(tmp_path, "prior-run", context=RunContext())
    ledger.write("briefs", {"kind": "brief", "stance": "porous", "theme": "rooms",
                            "text": "reach", "palette_notes": [], "forbidden_moves": [],
                            "sources": [], "thin": False, "carried_forward": True})
    conductor = _conductor(tmp_path, rounds_override=2, smoke=True)
    conductor._direct(conductor.schedule.set_plan(0))
    (direction,) = [r for r in _conductor_rows(tmp_path) if r["kind"] == "direction"]
    assert direction["has_brief"] is True
    assert direction["direction"]["theme"] == "rooms"


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
    # The finished round's spend was still counted.
    assert conductor.budget.spent_today == 3


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
    assert {r["player"] for r in persona_rows} == {"silt", "rust", "keep"}
    assert all(r["version"] == 1 for r in persona_rows)
    for player in conductor.players:
        assert player.self_state.version == 1
        assert player.self_state.residue["era"] == 1


def test_cap_reached_blocks_the_set(tmp_path: Path):
    conductor = _conductor(tmp_path, cap=5, rounds_override=2, smoke=True)
    # 2 rounds x 3 players = 6 projected > cap 5.
    assert conductor.budget.would_exceed(2 * len(conductor.players))


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
    assert any(p.name.startswith("2") and "smoke-set-" in p.name for p in smoke_root.iterdir())
