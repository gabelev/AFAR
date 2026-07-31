"""The staff at the set boundary: the Producer's cut and the Critic's word.

Offline end to end. A mock set is played (MockProvider + MockRenderer +
MockEmbedder), then the staff run retrospectively on its log. Under test:
the Producer's selection mechanics (panel winner, dissents, the choose()==-1
'no release' verdict), the Critic's naming call seeing ONLY finished work,
staff rows being strictly appended, and run_staff producing a superseding
content-addressed release record on a fixture mini-run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from ensemble.providers.model import Message, MockProvider

from afar.agents.critic import CriticAgent
from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.agents.producer import ProducerAgent
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.staff import load_set_view, newest_release_path, run_staff
from afar.run import run_set

_PLAYERS = ("silt", "rust", "keep")
_ROUNDS = 3
_RUN_ID = "test-staff-run"


def _mock_config(runs_root: Path, responder=_mock_players) -> AfarConfig:
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
    config = _mock_config(tmp_path)
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
    return [json.loads(line) for line in path.read_text().splitlines()]


def _listed(text: str, prefix: str) -> list[str]:
    for line in text.splitlines():
        if line.startswith(prefix):
            return [tok.strip() for tok in line[len(prefix):].split(",") if tok.strip()]
    return []


def _scripted_judges(score_table):
    """A responder whose judge scores come from score_table[grounding][player][round];
    staff prompts other than judging fall through to the offline mocks."""

    def responder(messages):
        text = "\n".join(m.content for m in messages)
        if '"scores"' in text and "ROUNDS:" in text:
            grounding = re.search(r"GROUNDING — ([a-z-]+):", text).group(1)
            player = re.search(r"ACT: (\w+)", text).group(1)
            rounds = _listed(text, "ROUNDS:")
            return json.dumps(
                {
                    "scores": {
                        r: {
                            "score": score_table[grounding][player][int(r)],
                            "why": f"{grounding} on {player} r{r}",
                        }
                        for r in rounds
                    }
                }
            )
        return _mock_players(messages)

    return responder


# --- Producer selection mechanics --------------------------------------------


def test_producer_picks_the_panel_winner_with_dissents(played_run: Path):
    # silt: round 1 unanimous. rust: min-score puts round 0 ahead (arc loves it),
    # but intent-fidelity and distinctness each prefer round 2 -> two dissents.
    flat = {r: 0.8 for r in range(_ROUNDS)}
    table = {
        "intent-fidelity": {
            "silt": {0: 0.6, 1: 0.9, 2: 0.6},
            "rust": {0: 0.70, 1: 0.60, 2: 0.75},
            "keep": flat,
        },
        "arc": {
            "silt": {0: 0.6, 1: 0.9, 2: 0.6},
            "rust": {0: 0.90, 1: 0.60, 2: 0.58},
            "keep": flat,
        },
        "distinctness": {
            "silt": {0: 0.6, 1: 0.9, 2: 0.6},
            "rust": {0: 0.70, 1: 0.60, 2: 0.72},
            "keep": flat,
        },
    }
    view = load_set_view(played_run)
    producer = ProducerAgent(MockProvider(responder=_scripted_judges(table)))
    selection = producer.select(view)

    assert selection.released
    assert selection.takes["silt"].round == 1
    assert selection.takes["silt"].dissents == []
    # rust: min scores r0=0.70, r1=0.60, r2=0.58 -> r0 wins the ordering and
    # passes every judge; two judges preferred another round -> dissents.
    assert selection.takes["rust"].round == 0
    dissenting = {d["judge"]: d["preferred_round"] for d in selection.takes["rust"].dissents}
    assert dissenting == {"intent-fidelity": 2, "distinctness": 2}
    # keep: flat scores -> the later round wins the tie (the take that heard more).
    assert selection.takes["keep"].round == _ROUNDS - 1
    # The paper trail rides along.
    assert selection.takes["rust"].scores["arc"] == 0.90
    assert "arc on rust r0" in selection.takes["rust"].reasoning
    assert selection.note  # public prose exists


def test_producer_no_release_when_the_panel_passes_nothing(played_run: Path):
    # Every rust take fails the arc judge's threshold -> choose() returns -1
    # for rust -> the whole set is a 'no release' verdict, not a forced cut.
    flat_good = {r: 0.8 for r in range(_ROUNDS)}
    flat_bad = {r: 0.2 for r in range(_ROUNDS)}
    table = {
        "intent-fidelity": {"silt": flat_good, "rust": flat_good, "keep": flat_good},
        "arc": {"silt": flat_good, "rust": flat_bad, "keep": flat_good},
        "distinctness": {"silt": flat_good, "rust": flat_good, "keep": flat_good},
    }
    view = load_set_view(played_run)
    producer = ProducerAgent(MockProvider(responder=_scripted_judges(table)))
    selection = producer.select(view)

    assert not selection.released
    assert selection.takes == {}
    assert selection.failed_players == ("rust",)
    assert "No release from this set" in selection.note


# --- Critic: naming only sees finished work -----------------------------------


def test_critic_naming_sees_only_the_selection(played_run: Path):
    view = load_set_view(played_run)
    provider = MockProvider(responder=_mock_players)
    selection = ProducerAgent(provider).select(view)
    critic = CriticAgent(provider)
    review = critic.review(view, selection)
    names = critic.name(selection, review)

    assert names.release_title
    assert set(names.take_titles) == set(_PLAYERS)

    naming_call = provider.calls[-1]
    naming_text = "\n".join(m.content for m in naming_call)
    # Finished work only: the selected takes' words and the review — never the
    # discarded rounds' material, rationales, or the measured story.
    selected_rounds = {pid: selection.takes[pid].round for pid in _PLAYERS}
    for pid in _PLAYERS:
        for take in view.takes[pid]:
            if take.round == selected_rounds[pid]:
                # First lyric line only: json.dumps escapes the newlines.
                assert take.lyrics.splitlines()[0] in naming_text
            else:  # a discarded take's sung words must not reach the naming call
                assert take.rationale not in naming_text
    assert "THE MEASURED STORY" not in naming_text
    assert review.release in naming_text


# --- run_staff: the boundary orchestrator --------------------------------------


def test_run_staff_appends_rows_and_supersedes_the_record(played_run: Path):
    run_dir = played_run
    config = _mock_config(run_dir.parent)
    old_release_path = newest_release_path(run_dir)
    old_record = json.loads(old_release_path.read_text())
    before = {
        table: (run_dir / f"{table}.jsonl").read_text()
        for table in ("intents", "artifacts", "embeddings", "features", "releases")
    }

    result = run_staff(run_dir, config)

    # Strictly appended: every pre-existing file's old bytes are a prefix.
    for table, old_bytes in before.items():
        assert (run_dir / f"{table}.jsonl").read_text().startswith(old_bytes)
    assert old_release_path.read_text() == json.dumps(old_record, indent=2, ensure_ascii=False) + "\n"

    # selections: one row per act plus the summary verdict row.
    selections = _rows(run_dir, "selections")
    assert [row["kind"] for row in selections] == ["take"] * 3 + ["selection"]
    assert {row["player"] for row in selections[:3]} == set(_PLAYERS)
    for row in selections[:3]:
        assert row["basis_release_id"] == old_record["release_id"]
        assert row["scores"] and row["take_id"] and row["intent_id"]
    assert selections[3]["released"] is True

    # reviews: per-act verdicts, the release verdict, then the titles — last.
    reviews = _rows(run_dir, "reviews")
    assert [row["kind"] for row in reviews] == ["act-review"] * 3 + ["release-review", "titles"]
    assert reviews[4]["release_title"] == "Mock Pressing"

    # The staff-enriched record supersedes the old one; the old file survives.
    record = result.release_record
    assert result.released
    assert record["provenance"]["supersedes_release_id"] == old_record["release_id"]
    assert record["provenance"]["staff"] == ["producer", "critic"]
    assert record["release_id"] != old_record["release_id"]
    assert result.release_path.exists()
    assert newest_release_path(run_dir) == result.release_path
    assert len(list(run_dir.glob("release-*.json"))) == 2
    # The interaction facts are untouched — staff adds, never edits.
    for key in ("influence", "convergence", "novelty", "asymmetry", "rounds", "artifacts", "set"):
        assert record[key] == old_record[key]
    # The staff block carries the cut and the word.
    staff = record["staff"]
    assert set(staff["producer"]["selected"]) == set(_PLAYERS)
    for pid in _PLAYERS:
        sel = staff["producer"]["selected"][pid]
        assert sel["take_id"] == old_record["artifacts"][sel["round"]][pid]
    assert staff["critic"]["release_title"] == "Mock Pressing"
    assert set(staff["critic"]["act_reviews"]) == set(_PLAYERS)
    # Logged as a releases row too.
    assert [row["id"] for row in _rows(run_dir, "releases")][-1] == record["release_id"]


def test_run_staff_logs_the_no_release_verdict_and_writes_no_record(played_run: Path):
    run_dir = played_run
    flat_bad = {r: 0.2 for r in range(_ROUNDS)}
    flat_good = {r: 0.8 for r in range(_ROUNDS)}
    table = {
        "intent-fidelity": {"silt": flat_good, "rust": flat_good, "keep": flat_bad},
        "arc": {"silt": flat_good, "rust": flat_good, "keep": flat_good},
        "distinctness": {"silt": flat_good, "rust": flat_good, "keep": flat_good},
    }
    config = _mock_config(run_dir.parent, responder=_scripted_judges(table))

    result = run_staff(run_dir, config)

    assert not result.released
    assert result.release_record is None and result.release_path is None
    selections = _rows(run_dir, "selections")
    verdict = selections[-1]
    assert verdict["kind"] == "selection" and verdict["released"] is False
    assert verdict["failed_players"] == ["keep"]
    assert "No release from this set" in verdict["note"]
    assert not (run_dir / "reviews.jsonl").exists()  # the Critic never ran
    assert len(list(run_dir.glob("release-*.json"))) == 1  # nothing superseded
