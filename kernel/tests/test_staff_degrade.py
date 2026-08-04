"""The degradation doctrine: a completed set is never voided by staff failure.

EXPERIMENT-ONLY: these cover the ROUND-BASED instrument (afar.staff_rounds,
behind AFAR_EXPERIMENT_MODE) — the panel, the cut, the veto, the Critic's
naming call, the Muse's brief. None of it runs on an album; the live album
reactions are tested in test_reactions.py.
The same doctrine on the album side (a failed reaction never blocks or alters
a release) is tested in test_reactions.py.

The stranded-set lesson (run 20260731-175857-set-0001-contact: 10 paid
rounds voided by one empty judge reply), now law — DECISIONS.md: the material
always outranks the commentary. Each staff stage is wrapped individually in
`run_staff`; a stage that still fails after the retry ladder logs a
`staff_stage_failed` row in its home table and the chain continues with that
piece absent. The matrix under test: each stage failing alone (and all four
failing together) still yields a release record that PUBLISHES, with honest
gaps — mechanical final-round cut, "Untitled Session NNNN", absent brief and
reaction. Only the Producer's deliberate 'no release' verdict withholds one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.publish import build_release_row, publish_run, read_jsonl, selected_takes
from afar.render.base import MockRenderer
from afar.run import run_set
from afar.staff import newest_release_path
from afar.staff_rounds import run_staff

_PLAYERS = ("silt", "rust", "keep")
_ROUNDS = 3
_RUN_ID = "test-degrade-run"

#: How each staff stage's prompts are recognized (markers ride the prompt text,
#: so they persist through the ladder's nudged re-prompts too).
_STAGE_MARKERS: dict[str, tuple[str, ...]] = {
    "producer": ('"scores"', "ROUNDS:"),  # the panel's judges
    "critic": ("The set is finished and cut. Review it.",),
    "critic-naming": ("Write its sleeve",),
    "muse": ("Write the brief",),
    "listener": ('"valence"', '"disagreements_with_critic"'),
}


def _failing(*stages: str, reply: str = ""):
    """A responder that PERSISTENTLY breaks the given stages' model calls
    (empty reply by default — the observed failure) and stays the offline
    mock for everything else."""

    def responder(messages):
        text = "\n".join(m.content for m in messages)
        for stage in stages:
            if all(marker in text for marker in _STAGE_MARKERS[stage]):
                return reply
        return _mock_players(messages)

    return responder


def _config(runs_root: Path, responder) -> AfarConfig:
    return AfarConfig(
        model=MockProvider(responder=responder),
        renderer=MockRenderer(runs_root / "audio"),
        runs_root=runs_root,
        live=False,
        code_sha="test-sha",
    )


@pytest.fixture
def played_run(tmp_path: Path) -> Path:
    """One full mock set logged under tmp_path/<_RUN_ID>; returns the run dir."""
    config = _config(tmp_path, _mock_players)
    ledger = JsonlLedger(tmp_path, _RUN_ID, context=RunContext(code_sha="test-sha"))
    players = [Player(PERSONAS[pid], config.model, config.renderer) for pid in _PLAYERS]
    run_set(
        players,
        rounds=_ROUNDS,
        condition="contact",
        config=config,
        ledger=ledger,
        embedder=MockEmbedder(),
        seed=7,
    )
    return tmp_path / _RUN_ID


def _rows(run_dir: Path, table: str) -> list[dict]:
    path = run_dir / f"{table}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _newest_record(run_dir: Path) -> dict:
    return json.loads(newest_release_path(run_dir).read_text())


def _release_row(run_dir: Path, release_id: str = "0005") -> dict:
    record = _newest_record(run_dir)
    takes = selected_takes(record)
    intents = read_jsonl(run_dir / "intents.jsonl")
    take_intents = {
        pid: next(r for r in intents if r["player"] == pid and r["round"] == takes[pid]["round"])
        for pid in _PLAYERS
    }
    return build_release_row(release_id, record, run_dir.name, take_intents)


# --- the matrix: each stage failing alone still publishes ----------------------


def test_producer_failure_degrades_to_the_mechanical_final_round(played_run: Path):
    config = _config(played_run.parent, _failing("producer"))
    result = run_staff(played_run, config)

    # The set releases anyway: the final round's takes stand, mechanically.
    assert result.released
    assert result.degraded == ("producer",)
    assert all(c.round == _ROUNDS - 1 for c in result.selection.takes.values())
    (failed_row,) = [r for r in _rows(played_run, "selections") if r["kind"] == "staff_stage_failed"]
    assert failed_row["agent"] == "producer" and failed_row["error"]

    # The record carries no Producer block, an honest degradation note, and
    # the rest of the chain STILL RAN (Critic titled it; Muse + Listener spoke).
    record = _newest_record(played_run)
    assert "producer" not in record["staff"]
    assert "did not file" in record["staff_degraded"]["producer"]["note"]
    assert "producer" in record["provenance"]["staff_degraded"]
    assert record["staff"]["critic"]["release_title"] == "Mock Pressing"
    assert "muse" in record["staff"] and "listener" in record["staff"]

    # Publish proceeds: mechanical fallback takes, honest selection prose.
    assert {pid: t["round"] for pid, t in selected_takes(record).items()} == {
        pid: _ROUNDS - 1 for pid in _PLAYERS
    }
    row = _release_row(played_run)
    assert "did not file" in row["selection"]
    assert "mechanically" in row["metadata"]["producerSelection"]
    outcome = publish_run(played_run, dry_run=True, release_id="0005")
    assert outcome.release_title == "Mock Pressing"


def test_critic_failure_degrades_to_an_untitled_session(played_run: Path):
    config = _config(played_run.parent, _failing("critic", "critic-naming"))
    result = run_staff(played_run, config)

    assert result.released
    assert result.degraded == ("critic",)
    assert result.review is None and result.names is None
    (failed_row,) = [r for r in _rows(played_run, "reviews") if r["kind"] == "staff_stage_failed"]
    assert failed_row["agent"] == "critic"

    record = _newest_record(played_run)
    assert "critic" not in record["staff"]
    assert "producer" in record["staff"]  # the cut still filed
    assert record["staff_degraded"]["critic"]["note"] == "The Critic did not file this time."

    row = _release_row(played_run, "0005")
    assert row["title"] == "Untitled Session 0005"
    assert row["metadata"]["titlePlaceholder"] is True
    assert row["metadata"]["titledBy"] is None
    assert row["review"] == "The Critic did not file this time."
    outcome = publish_run(played_run, dry_run=True, release_id="0005")
    assert outcome.release_title == "Untitled Session 0005"


def test_critic_naming_failure_alone_degrades_the_whole_critic_stage(played_run: Path):
    # The name is half the Critic's job; a review without a title is not filed.
    config = _config(played_run.parent, _failing("critic-naming"))
    result = run_staff(played_run, config)
    assert result.released
    assert result.degraded == ("critic",)
    assert [r["kind"] for r in _rows(played_run, "reviews")] == ["staff_stage_failed"]


def test_muse_failure_leaves_the_brief_absent(played_run: Path):
    config = _config(played_run.parent, _failing("muse"))
    result = run_staff(played_run, config)

    assert result.released
    assert result.degraded == ("muse",)
    assert result.brief is None and result.reaction is not None
    (failed_row,) = [r for r in _rows(played_run, "briefs") if r["kind"] == "staff_stage_failed"]
    assert failed_row["agent"] == "muse"
    assert not [r for r in _rows(played_run, "briefs") if r["kind"] == "brief"]

    record = _newest_record(played_run)
    assert "muse" not in record["staff"] and "listener" in record["staff"]
    assert record["provenance"]["staff"] == ["producer", "critic", "listener", "archivist"]
    row = _release_row(played_run)
    assert "The Muse did not file" in row["brief"]
    publish_run(played_run, dry_run=True, release_id="0005")


def test_listener_failure_leaves_the_reaction_absent(played_run: Path):
    config = _config(played_run.parent, _failing("listener", reply="I loved it!! five stars"))
    result = run_staff(played_run, config)

    assert result.released
    assert result.degraded == ("listener",)
    assert result.brief is not None and result.reaction is None
    (failed_row,) = [r for r in _rows(played_run, "reactions") if r["kind"] == "staff_stage_failed"]
    assert failed_row["agent"] == "listener"

    record = _newest_record(played_run)
    assert "listener" not in record["staff"] and "muse" in record["staff"]
    row = _release_row(played_run)
    assert row["reaction"] == "The Listener did not file this time."
    assert "reactionValence" not in row
    publish_run(played_run, dry_run=True, release_id="0005")


def test_every_stage_failing_still_publishes_with_honest_gaps(played_run: Path):
    config = _config(
        played_run.parent,
        _failing("producer", "critic", "critic-naming", "muse", "listener"),
    )
    result = run_staff(played_run, config)

    assert result.released
    assert result.degraded == ("producer", "critic", "muse", "listener")
    record = _newest_record(played_run)
    # The Archivist (unbroken here) still shelved the wreckage — its whole
    # job is believing exactly this material is worth keeping.
    assert set(record["staff"]) == {"archivist"}
    assert set(record["staff_degraded"]) == {"producer", "critic", "muse", "listener"}
    assert record["provenance"]["staff"] == ["archivist"]

    row = _release_row(played_run, "0005")
    assert row["title"] == "Untitled Session 0005"
    for field, phrase in (
        ("selection", "did not file"),
        ("review", "did not file"),
        ("brief", "did not file"),
        ("reaction", "did not file"),
    ):
        assert phrase in row[field], field
    outcome = publish_run(played_run, dry_run=True, release_id="0005")
    assert outcome.release_title == "Untitled Session 0005"
    assert outcome.timeline_blocks == 1


def test_the_no_release_verdict_is_a_decision_not_a_degradation(played_run: Path):
    # A panel that convened and passed nothing still withholds the release —
    # degradation is for FAILED stages, never for the Producer's judgment.
    def low_scoring_judges(messages):
        text = "\n".join(m.content for m in messages)
        if all(marker in text for marker in _STAGE_MARKERS["producer"]):
            rounds = re.search(r"^ROUNDS: (.+)$", text, re.MULTILINE).group(1).split(",")
            return json.dumps(
                {"scores": {r.strip(): {"score": 0.1, "why": "flat"} for r in rounds}}
            )
        return _mock_players(messages)

    config = _config(played_run.parent, low_scoring_judges)
    result = run_staff(played_run, config)
    assert not result.released
    assert result.degraded == ()
    assert result.release_record is None
    assert len(list(played_run.glob("release-*.json"))) == 1  # nothing superseded
