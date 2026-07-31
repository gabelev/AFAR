"""The Archivist and the vault: where everything belongs.

Offline end to end (MockProvider/MockRenderer/MockEmbedder). Under test:
`load_tape_view` reading ANY run tolerantly (a staffed session, a vetoed
session, a solo step-a run, an abandoned mid-set run), the Archivist's one
decision (`shelve` — placement + sleeve) and its degrade path, the archives
rows, and the published tape row shape (`build_tape_row` / `publish_tape`) —
including the honest framing of a rejected session's tape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ensemble.providers.model import MockProvider

from afar.agents.archivist import ArchivistAgent, PLACEMENTS, Shelving, tape_digest
from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.archive import load_tape_view, newest_shelving
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.publish import build_tape_row, next_tape_id, publish_tape
from afar.render.base import MockRenderer
from afar.run import run_set
from afar.staff import STAGE_NAMES, run_archivist, run_staff

_PLAYERS = ("silt", "rust", "keep")
_ROUNDS = 3
_RUN_ID = "20990101-000000-set-0000-contact"


def _config(runs_root: Path, responder=_mock_players) -> AfarConfig:
    return AfarConfig(
        model=MockProvider(responder=responder),
        renderer=MockRenderer(runs_root / "audio"),
        runs_root=runs_root,
        live=False,
        code_sha="test-sha",
    )


def _play(tmp_path: Path, run_id: str = _RUN_ID) -> Path:
    config = _config(tmp_path)
    ledger = JsonlLedger(tmp_path, run_id, context=RunContext(code_sha="test-sha"))
    players = [Player(PERSONAS[pid], config.model, config.renderer) for pid in _PLAYERS]
    run_set(
        players, rounds=_ROUNDS, condition="contact", config=config, ledger=ledger,
        embedder=MockEmbedder(), seed=7,
    )
    return tmp_path / run_id


def _rows(run_dir: Path, table: str) -> list[dict]:
    path = run_dir / f"{table}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- load_tape_view: any run, read whole ---------------------------------------


def test_tape_view_reads_a_staffed_session_whole(tmp_path: Path):
    run_dir = _play(tmp_path)
    run_staff(run_dir, _config(tmp_path))
    view = load_tape_view(run_dir)
    assert view.kind == "session" and view.condition == "contact"
    assert view.players == _PLAYERS and view.rounds == _ROUNDS
    assert len(view.takes) == _ROUNDS * 3 and view.complete
    # Round order, always — the tape plays the session as it happened.
    assert [t.round for t in view.takes] == sorted(t.round for t in view.takes)
    assert view.released and view.status == "released"
    assert set(view.selected) == set(_PLAYERS)
    assert view.veto_note is None


def test_tape_view_reads_a_solo_run_without_runs_jsonl(tmp_path: Path):
    # A step-a run has ONLY intents + artifacts — no runs.jsonl, no record.
    run_dir = _play(tmp_path)
    for name in ("runs.jsonl", "rounds.jsonl", "sets.jsonl", "embeddings.jsonl", "features.jsonl"):
        (run_dir / name).unlink(missing_ok=True)
    for extra in run_dir.glob("release-*.json"):
        extra.unlink()
    view = load_tape_view(run_dir)
    assert view.kind == "solo" and view.condition == "solo"
    assert view.status == "solo" and not view.released
    assert view.rounds == _ROUNDS and view.complete


def test_tape_view_reads_an_abandoned_session_honestly(tmp_path: Path):
    # Drop the final round's artifacts: the render died mid-set.
    run_dir = _play(tmp_path)
    artifacts = _rows(run_dir, "artifacts.jsonl"[: -len(".jsonl")])
    kept = [r for r in artifacts if r["round"] < _ROUNDS - 1]
    (run_dir / "artifacts.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in kept)
    )
    for extra in run_dir.glob("release-*.json"):
        extra.unlink()
    view = load_tape_view(run_dir)
    assert not view.complete
    assert view.status == "abandoned"
    assert len(view.takes) == (_ROUNDS - 1) * 3


def test_tape_view_reads_the_veto(tmp_path: Path):
    run_dir = _play(tmp_path)
    ledger = JsonlLedger(tmp_path, _RUN_ID, context=RunContext(code_sha="test-sha"))
    ledger.write(
        "selections",
        {"kind": "selection", "agent": "producer", "released": False,
         "note": "No release from this set. Nothing cleared the panel."},
    )
    view = load_tape_view(run_dir)
    assert not view.released
    assert view.status == "rejected"
    assert "Nothing cleared the panel" in view.veto_note


def test_tape_view_requires_the_material_itself(tmp_path: Path):
    empty = tmp_path / "empty-run"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        load_tape_view(empty)


# --- the Archivist's one decision ----------------------------------------------


def test_shelve_returns_a_placement_and_a_sleeve(tmp_path: Path):
    run_dir = _play(tmp_path)
    run_staff(run_dir, _config(tmp_path))
    archivist = ArchivistAgent(_config(tmp_path).model)
    shelving = archivist.shelve(load_tape_view(run_dir), stage_names=STAGE_NAMES)
    assert isinstance(shelving, Shelving)
    assert shelving.placement in PLACEMENTS
    assert shelving.tape_title and shelving.arc and shelving.notes


def test_the_archivist_reads_the_whole_tape_not_the_cut(tmp_path: Path):
    run_dir = _play(tmp_path)
    run_staff(run_dir, _config(tmp_path))
    provider = MockProvider(responder=_mock_players)
    ArchivistAgent(provider).shelve(load_tape_view(run_dir), stage_names=STAGE_NAMES)
    prompt = "\n".join(m.content for m in provider.calls[-1])
    # Every round is in the Archivist's hands, by stage name, cut marked.
    assert "Delta Marlowe" in prompt and "on_the_release" in prompt
    assert prompt.count('"round": 0') >= 3 and prompt.count(f'"round": {_ROUNDS - 1}') >= 3


def test_tape_digest_marks_cut_and_dissent(tmp_path: Path):
    run_dir = _play(tmp_path)
    run_staff(run_dir, _config(tmp_path))
    view = load_tape_view(run_dir)
    # Splice a dissent in: a judge wanted silt's round 0.
    view = type(view)(**{**view.__dict__, "dissents": {"silt": [
        {"judge": "arc", "preferred_round": 0, "rationale": "the opening held more"}
    ]}})
    digest = tape_digest(view, STAGE_NAMES)
    selected = [e for e in digest if e.get("on_the_release")]
    assert len(selected) == 3
    (dissent_entry,) = [e for e in digest if "dissent" in e]
    assert dissent_entry["round"] == 0 and dissent_entry["act"] == "Delta Marlowe"
    assert "arc judge preferred round 0" in dissent_entry["dissent"]


# --- run_archivist: the stage, its rows, its degrade path ----------------------


def test_run_archivist_shelves_a_vetoed_session_without_a_release(tmp_path: Path):
    run_dir = _play(tmp_path)
    ledger = JsonlLedger(tmp_path, _RUN_ID, context=RunContext(code_sha="test-sha"))
    ledger.write(
        "selections",
        {"kind": "selection", "agent": "producer", "released": False,
         "note": "No release from this set."},
    )
    releases_before = len(list(run_dir.glob("release-*.json")))
    outcome = run_archivist(run_dir, _config(tmp_path))
    assert outcome.shelving is not None and outcome.liner_notes is None
    assert outcome.degraded == ()
    # No release record superseded — the archives row IS the shelving.
    assert len(list(run_dir.glob("release-*.json"))) == releases_before
    row = newest_shelving(run_dir)
    assert row["status"] == "rejected" and row["release_liner_notes"] is None


def test_run_archivist_degrades_never_voids(tmp_path: Path):
    run_dir = _play(tmp_path)

    def broken_archivist(messages):
        text = "\n".join(m.content for m in messages)
        if "Shelve this session's tape" in text or "Write the liner notes for this release" in text:
            return ""  # the observed failure mode: an empty staff reply
        return _mock_players(messages)

    # The WHOLE chain runs with a broken Archivist: everything else files,
    # the set still releases, the tape publishes unshelved.
    result = run_staff(run_dir, _config(tmp_path, responder=broken_archivist))
    assert result.released
    assert result.degraded == ("archivist",)
    assert result.shelving is None and result.liner_notes is None
    (failed,) = [r for r in _rows(run_dir, "archives") if r["kind"] == "staff_stage_failed"]
    assert failed["agent"] == "archivist" and failed["error"]
    assert "unshelved" in failed["note"]
    record = json.loads(sorted(run_dir.glob("release-*.json"),
                               key=lambda p: p.stat().st_mtime)[-1].read_text())
    assert "archivist" not in record.get("staff", {})
    # The tape still publishes, unshelved and honest.
    tape = publish_tape(run_dir, release_id="0005", dry_run=True)
    assert tape.shelved is False and tape.takes == _ROUNDS * 3


# --- the published tape row (the web contract) ---------------------------------


def test_build_tape_row_matches_the_web_contract(tmp_path: Path):
    run_dir = _play(tmp_path)
    run_staff(run_dir, _config(tmp_path))
    view = load_tape_view(run_dir)
    shelving = newest_shelving(run_dir)
    row = build_tape_row("0007", view, shelving, release_id="0005")
    assert row["id"] == "0007" and row["kind"] == "tape"
    assert row["releaseId"] == "0005" and row["runId"] == _RUN_ID
    assert row["date"] == "2099-01-01" and row["rounds"] == _ROUNDS
    assert row["status"] == "released"
    assert row["placement"] in PLACEMENTS and row["arc"] and row["linerNotes"]
    assert len(row["takes"]) == _ROUNDS * 3
    for take in row["takes"]:
        assert take["agentId"] in _PLAYERS
        assert take["audioUrl"].startswith("/api/media/")
        assert isinstance(take["selected"], bool)
        assert take["durationSec"] == 30
    # Selected takes carry the Critic's titles; the rest stay untitled.
    titled = [t for t in row["takes"] if t["selected"]]
    assert all(t["title"] for t in titled)
    assert all(t["title"] is None for t in row["takes"] if not t["selected"])


def test_tape_row_frames_the_veto_honestly(tmp_path: Path):
    run_dir = _play(tmp_path)
    ledger = JsonlLedger(tmp_path, _RUN_ID, context=RunContext(code_sha="test-sha"))
    ledger.write(
        "selections",
        {"kind": "selection", "agent": "producer", "released": False,
         "note": "No release from this set. Rust's takes never settled."},
    )
    run_archivist(run_dir, _config(tmp_path))
    row = build_tape_row("0001", load_tape_view(run_dir), newest_shelving(run_dir))
    assert row["status"] == "rejected"
    assert row["releaseId"] is None
    # Display shim: the veto note's quoted internal name shows as first name.
    assert "Roan's takes never settled" in row["vetoNote"]
    assert not any(t["selected"] for t in row["takes"])


def test_tape_row_normalizes_pre_voice_fix_lines(tmp_path: Path):
    run_dir = _play(tmp_path)
    intents = _rows(run_dir, "intents")
    intents[0]["line"] = "Keep, I left the gap for you — the silt can wait."
    (run_dir / "intents.jsonl").write_text("".join(json.dumps(r) + "\n" for r in intents))
    row = build_tape_row("0001", load_tape_view(run_dir), None)
    lines = [t["line"] for t in row["takes"]]
    assert any("Evers, I left the gap" in l for l in lines)
    assert not any(l.startswith("Keep,") for l in lines)
    # Common-noun uses survive untouched (the shim's law).
    assert any("the silt can wait" in l for l in lines)


def test_next_tape_id_counts_the_series():
    assert next_tape_id([]) == "0001"
    assert next_tape_id(["0001", "0002"]) == "0003"


def test_publish_tape_dry_run_touches_nothing(tmp_path: Path):
    run_dir = _play(tmp_path)
    run_staff(run_dir, _config(tmp_path))
    outcome = publish_tape(run_dir, release_id="0005", dry_run=True)
    assert outcome.dry_run and outcome.tape_id == "0000"
    assert outcome.takes == _ROUNDS * 3
    assert outcome.media_bytes > 0 and outcome.shelved
