"""afar.publish: the Python publish path, oracle-pinned to publish_set.mjs.

The pure helpers carry the same fixtures as web/scripts/publish_set.test.ts,
so the two ports cannot drift apart silently. The end-to-end tests run over a
REAL mock set (played + staff-walked in tmp), publish dry (nothing external),
then publish against a fake injected connection and assert exactly what would
land in Neon — media, tracks, release, and the compiled timeline_source row
the web route prefers.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.publish import (
    PLAYER_IDS,
    brief_prose,
    build_release_row,
    build_track_rows,
    compile_timeline_block,
    compile_timeline_blocks,
    newest_release_record_file,
    next_release_id,
    normalized_influence,
    publish_run,
    reaction_prose,
    selected_takes,
    timeline_staff,
)
from afar.render.base import MockRenderer
from afar.run import run_set
from afar.staff import run_staff

_ARTIFACTS = [
    {"silt": "s0", "rust": "r0", "keep": "k0"},
    {"silt": "s1", "rust": "r1", "keep": "k1"},
    {"silt": "s2", "rust": "r2", "keep": "k2"},
]


# --- pure helpers (same oracles as publish_set.test.ts) -----------------------


def test_selected_takes_publishes_the_producers_cut_spanning_rounds():
    record = {
        "set": {"rounds": 3},
        "artifacts": _ARTIFACTS,
        "staff": {
            "producer": {
                "selected": {
                    "silt": {"round": 0, "take_id": "s0"},
                    "rust": {"round": 2, "take_id": "r2"},
                    "keep": {"round": 1, "take_id": "k1"},
                }
            }
        },
    }
    assert selected_takes(record) == {
        "silt": {"round": 0, "hash": "s0"},
        "rust": {"round": 2, "hash": "r2"},
        "keep": {"round": 1, "hash": "k1"},
    }


def test_selected_takes_falls_back_to_the_final_round_pre_staff():
    record = {"set": {"rounds": 3}, "artifacts": _ARTIFACTS}
    assert selected_takes(record) == {
        "silt": {"round": 2, "hash": "s2"},
        "rust": {"round": 2, "hash": "r2"},
        "keep": {"round": 2, "hash": "k2"},
    }


def test_brief_prose_labels_carried_forward_and_keeps_placeholders():
    prose = brief_prose({"muse": {"text": "Reach for the seam.", "carried_forward": True}})
    assert "carried forward into the next session" in prose
    assert "Reach for the seam." in prose
    assert brief_prose({"muse": {"text": "Reach.", "carried_forward": False}}) == "Reach."
    assert brief_prose(None) is None
    assert brief_prose({"producer": {}}) is None
    assert brief_prose({"muse": {"text": ""}}) is None


def test_reaction_prose_ships_the_listeners_words_untouched():
    assert reaction_prose({"listener": {"valence": "mixed", "text": "Played it twice."}}) == (
        "Played it twice."
    )
    assert reaction_prose(None) is None
    assert reaction_prose({"listener": {"text": ""}}) is None


def test_normalized_influence_min_max_normalizes_the_final_round():
    record = {
        "set": {"rounds": 2},
        "influence": {"intent": {"1": {"silt<-rust": -0.2, "rust<-silt": 0.6, "keep<-silt": 0.2}}},
    }
    edges = {(e["to"], e["from"]): e["weight"] for e in normalized_influence(record)}
    assert edges[("silt", "rust")] == 0.0
    assert edges[("rust", "silt")] == 1.0
    assert edges[("keep", "silt")] == 0.5
    # Doors-closed sets can have no edges: an empty list IS the honest cover.
    assert normalized_influence({"set": {"rounds": 2}, "influence": {"intent": {}}}) == []


def test_next_release_id_counts_past_the_numeric_catalogue():
    assert next_release_id([]) == "0001"
    assert next_release_id(["0001", "0002"]) == "0003"
    assert next_release_id(["0001", "junk", "0009"]) == "0010"


def test_newest_release_record_file_picks_mtime_not_name(tmp_path: Path):
    old = tmp_path / "release-121a7fea914e.json"
    new = tmp_path / "release-5aba762c21c9.json"  # sorts FIRST alphabetically
    old.write_text("{}")
    new.write_text("{}")
    now = time.time()
    os.utime(old, (now - 3600, now - 3600))
    os.utime(new, (now, now))
    assert newest_release_record_file(tmp_path) == new
    empty = tmp_path / "empty"
    empty.mkdir()
    assert newest_release_record_file(empty) is None


# --- a real mock run to publish -----------------------------------------------

_RUN_ID = "20990101-000000-set-0000-contact"


@pytest.fixture
def staffed_run(tmp_path: Path) -> Path:
    """One mock set, played and staff-walked, under tmp_path/<run>. Returns run dir."""
    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=MockRenderer(tmp_path / "audio"),
        runs_root=tmp_path,
        live=False,
        code_sha="test-sha",
    )
    ledger = JsonlLedger(tmp_path, _RUN_ID, context=RunContext(code_sha="test-sha"))
    players = [Player(PERSONAS[pid], config.model, config.renderer) for pid in PLAYER_IDS]
    run_set(
        players, rounds=3, condition="contact", config=config, ledger=ledger,
        embedder=MockEmbedder(), seed=7,
    )
    run_staff(tmp_path / _RUN_ID, config)
    return tmp_path / _RUN_ID


def test_release_row_matches_the_web_contract(staffed_run: Path):
    record = json.loads(newest_release_record_file(staffed_run).read_text())
    intents = [json.loads(l) for l in (staffed_run / "intents.jsonl").read_text().splitlines()]
    takes = selected_takes(record)
    take_intents = {
        pid: next(r for r in intents if r["player"] == pid and r["round"] == takes[pid]["round"])
        for pid in PLAYER_IDS
    }
    row = build_release_row("0003", record, _RUN_ID, take_intents)

    # Exactly what web/lib/data.ts ReleaseSchema requires.
    for key in ("id", "title", "era", "set", "condition", "date", "brief", "selection",
                "review", "reaction", "takeIds", "influence", "rationales"):
        assert row.get(key) not in (None, "", []), f"missing/empty {key}"
    assert row["id"] == "0003" and row["set"] == 3
    assert row["date"] == "2099-01-01"
    assert row["takeIds"] == [f"0003-{pid}" for pid in PLAYER_IDS]
    assert row["title"] == "Mock Pressing"  # the Critic's title (mock staff)
    assert row["reactionValence"] in ("loved", "liked", "mixed", "cold")
    assert row["selections"] == {pid: f"0003-{pid}" for pid in PLAYER_IDS}
    for edge in row["influence"]:
        assert 0.0 <= edge["weight"] <= 1.0
        assert edge["from"] in PLAYER_IDS and edge["to"] in PLAYER_IDS
    assert row["metadata"]["runId"] == _RUN_ID
    assert row["metadata"]["titledBy"] == "the Critic"

    tracks = build_track_rows("0003", record, take_intents, _RUN_ID)
    assert [t["id"] for t in tracks] == [f"0003-{pid}" for pid in PLAYER_IDS]
    for t in tracks:
        assert t["audioUrl"].startswith("/api/media/")
        assert t["durationSec"] == 30
        assert t["titledBy"] == "the Critic"


def test_compile_timeline_block_matches_the_world_shape(staffed_run: Path):
    runs_root = staffed_run.parent
    record = json.loads(newest_release_record_file(staffed_run).read_text())
    row = {"title": "Mock Pressing", "era": "2020s", "set": 3, "condition": "contact",
           "metadata": {"runId": _RUN_ID}}
    block = compile_timeline_block("0003", row, _RUN_ID, runs_root)
    assert block["releaseId"] == "0003"
    assert block["rounds"] == record["set"]["rounds"]
    assert len(block["linesByRound"]) == block["rounds"]
    for frame in block["linesByRound"]:
        assert set(frame) == set(PLAYER_IDS)
    assert block["artifactsByRound"] == record["artifacts"]
    assert block["intentEdgesByRound"] == record["influence"]["intent"]
    assert block["names"] == {"silt": "Delta Marlowe", "rust": "Roan Patina", "keep": "Evers Lane"}

    # The staff-walked run carries its logged staff rows into the block —
    # the TimelineStaff shape the world's staff events compile from.
    staff = block["staff"]
    assert staff["producer"]["note"] == record["staff"]["producer"]["note"]
    assert staff["critic"]["releaseReview"] == record["staff"]["critic"]["release_review"]
    assert set(staff["critic"]["actReviews"]) == set(PLAYER_IDS)
    assert staff["muse"]["theme"] == record["staff"]["muse"]["theme"]
    assert staff["listener"]["text"] == record["staff"]["listener"]["text"]
    assert staff["listener"]["valence"] == record["staff"]["listener"]["valence"]

    # Rows without a runId (the seeded 0001) or a missing run dir are skipped.
    compiled = compile_timeline_blocks(
        [("0001", {"title": "Seeded"}),
         ("0002", {"metadata": {"runId": "not-a-dir"}}),
         ("0003", row)],
        runs_root,
    )
    assert [b["releaseId"] for b in compiled["blocks"]] == ["0003"]


def test_timeline_staff_same_oracle_as_compile_staff_in_mjs():
    """The SHARED oracle with web (compile_timeline.mjs compileStaff /
    timeline.test.ts "staff events compile from logged rows only"): the same
    record staff block must yield the same TimelineStaff, display shim
    applied, absent stages absent."""
    record = {
        "staff": {
            "producer": {"note": "kept the takes that held the room"},
            "critic": {
                "release_review": "A record that knows what it is.",
                "act_reviews": {
                    "keep": "Keep held the centre.",  # display shim: Keep -> Evers
                    "rust": "Rust has been coasting.",
                    "silt": "Silt buried the best phrase.",
                    "ghost": "not a player",  # unknown ids never ride along
                },
            },
            "muse": {"theme": "rooms after rain", "text": "Answer with water."},
            "listener": {"valence": "mixed", "text": "Played it twice."},
        }
    }
    staff = timeline_staff(record)
    assert staff == {
        "producer": {"note": "kept the takes that held the room"},
        "critic": {
            "releaseReview": "A record that knows what it is.",
            "actReviews": {
                "keep": "Evers held the centre.",
                "rust": "Roan has been coasting.",
                "silt": "Delta buried the best phrase.",
            },
        },
        "muse": {"theme": "rooms after rain", "text": "Answer with water."},
        "listener": {"valence": "mixed", "text": "Played it twice."},
    }


def test_timeline_staff_absent_stages_stay_absent():
    assert timeline_staff({}) is None
    assert timeline_staff({"staff": {}}) is None
    assert timeline_staff({"staff": {"producer": {}}}) is None  # no note logged
    partial = timeline_staff({"staff": {"listener": {"text": "Heard it once."}}})
    assert partial == {"listener": {"text": "Heard it once."}}
    # a degraded critic (no rows) stages nothing even beside a live muse
    mixed = timeline_staff({"staff": {"critic": {}, "muse": {"theme": "dust"}}})
    assert mixed == {"muse": {"theme": "dust"}}


def test_publish_dry_run_touches_nothing_external(staffed_run: Path):
    outcome = publish_run(staffed_run, dry_run=True)
    assert outcome.dry_run is True
    assert outcome.release_id == "0000"  # placeholder: no DB was asked
    assert outcome.release_title == "Mock Pressing"
    assert set(outcome.media) == set(PLAYER_IDS)
    assert all(size >= 1000 for size in outcome.media.values())
    assert outcome.track_ids == tuple(f"0000-{pid}" for pid in PLAYER_IDS)
    assert outcome.timeline_blocks == 1
    # The tape half is computed dry too — all 9 takes, nothing written.
    assert outcome.tape is not None and outcome.tape.dry_run is True
    assert outcome.tape.takes == 9 and outcome.tape.shelved is True


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    """Recording stand-in for a psycopg connection (jsonb passed raw)."""

    def __init__(self, existing_releases: dict[str, dict]):
        self.releases = dict(existing_releases)
        self.executed: list[tuple[str, tuple | None]] = []
        self.committed = False

    def execute(self, sql: str, params=None):
        self.executed.append((sql, params))
        if sql.startswith("SELECT id FROM releases"):
            return _FakeCursor([(rid,) for rid in self.releases])
        if sql.startswith("SELECT id, data FROM releases"):
            return _FakeCursor(sorted(self.releases.items()))
        if sql.startswith("INSERT INTO releases"):
            self.releases[params[0]] = params[1]
        return _FakeCursor([])

    def commit(self):
        self.committed = True


def test_publish_live_upserts_everything_and_writes_timeline_source(staffed_run: Path):
    conn = _FakeConn({"0001": {"title": "Seeded, no run"}})
    outcome = publish_run(staffed_run, connection=conn)

    assert outcome.dry_run is False
    assert outcome.release_id == "0002"  # allocated past the seeded 0001
    assert conn.committed

    statements = [sql for sql, _ in conn.executed]
    # media + tracks/releases/timeline_source, then the tape half re-ensures
    # media and creates tapes (the vault doctrine rides the same publish).
    assert sum(1 for s in statements if s.startswith("CREATE TABLE IF NOT EXISTS")) == 6
    # 3 selected takes + ALL 9 takes (content-addressed; selected upsert twice).
    assert sum(1 for s in statements if s.startswith("INSERT INTO media")) == 12
    assert sum(1 for s in statements if s.startswith("INSERT INTO tracks")) == 3
    assert sum(1 for s in statements if s.startswith("INSERT INTO releases")) == 1
    assert sum(1 for s in statements if s.startswith("INSERT INTO tapes")) == 1

    # Media rows are content-addressed and carry real bytes.
    media_params = [p for sql, p in conn.executed if sql.startswith("INSERT INTO media")]
    for hash_id, content_type, data in media_params:
        assert len(hash_id) == 64 and content_type == "audio/mpeg"
        assert len(data) >= 1000

    # The timeline_source row carries the whole compilable catalogue: the
    # seeded 0001 (no runId) is skipped, our release compiles to one block.
    (timeline_params,) = [p for sql, p in conn.executed
                          if sql.startswith("INSERT INTO timeline_source")]
    timeline = timeline_params[0]
    assert [b["releaseId"] for b in timeline["blocks"]] == ["0002"]
    assert timeline["blocks"][0]["runId"] == _RUN_ID
    assert outcome.timeline_blocks == 1

    # The session tape rode the same publish: TAPE-0001, every take, shelved
    # (the staffed fixture ran the full chain, Archivist included), pointing
    # home at the release it companions.
    assert outcome.tape is not None and outcome.tape.tape_id == "0001"
    (tape_params,) = [p for sql, p in conn.executed if sql.startswith("INSERT INTO tapes")]
    tape_row = tape_params[1]
    assert tape_row["kind"] == "tape" and tape_row["releaseId"] == "0002"
    assert tape_row["runId"] == _RUN_ID
    assert len(tape_row["takes"]) == 9
    assert [t["round"] for t in tape_row["takes"]] == sorted(t["round"] for t in tape_row["takes"])
    assert sum(1 for t in tape_row["takes"] if t["selected"]) == 3
    assert tape_row["status"] == "released" and tape_row["placement"]
    assert tape_row["linerNotes"]
