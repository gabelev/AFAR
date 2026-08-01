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
from afar.staff import (
    load_recent_tape_titles,
    load_recent_titles,
    load_set_view,
    newest_release_path,
    run_muse_listener,
    run_staff,
)
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


# --- Naming register: the shelf, the ruts, the shapes --------------------------


def _naming_setup(played_run: Path):
    view = load_set_view(played_run)
    provider = MockProvider(responder=_mock_players)
    selection = ProducerAgent(provider).select(view)
    critic = CriticAgent(provider)
    review = critic.review(view, selection)
    return provider, critic, selection, review


def test_critic_naming_prompt_carries_register_and_shelf(played_run: Path):
    provider, critic, selection, review = _naming_setup(played_run)
    shelf = ["Same Hole, Softer Hand", "Three Rooms, No Doors"]
    names = critic.name(selection, review, recent_titles=shelf)

    assert names.release_title
    naming_text = "\n".join(m.content for m in provider.calls[-1])
    # The known ruts are named and closed — including the second-audit pair
    # (bland verb-phrase fragments, bare generic nouns).
    assert "RUTS THE HOUSE HAS ALREADY WORN" in naming_text
    assert "two fragments joined by a comma" in naming_text
    assert 'beginning with "Same"' in naming_text
    assert "vague verb-phrase fragments" in naming_text
    assert "a bare generic noun" in naming_text
    # The concrete-noun doctrine is shown (with the never-reuse guard).
    assert "HOW A TITLE IS FOUND" in naming_text
    assert "names a THING" in naming_text
    assert "no other record could carry it" in naming_text
    assert "Undertow" in naming_text and "never reuse" in naming_text
    # And the shelf is visible, under the do-not-echo pressure.
    assert "ALREADY ON THE SHELF" in naming_text
    for title in shelf:
        assert title in naming_text


def test_critic_naming_prompt_omits_the_shelf_when_empty(played_run: Path):
    provider, critic, selection, review = _naming_setup(played_run)
    critic.name(selection, review)
    naming_text = "\n".join(m.content for m in provider.calls[-1])
    assert "ALREADY ON THE SHELF" not in naming_text
    assert "RUTS THE HOUSE HAS ALREADY WORN" in naming_text  # the rules always ride


def test_load_recent_titles_reads_the_shelf_across_runs(tmp_path: Path):
    for run_id, release, takes in (
        ("run-a", "Standing Water", {"silt": "Pour Again"}),
        ("run-b", "Two Thirds Warm", {"rust": "Pour Again"}),  # dupe take title
    ):
        ledger = JsonlLedger(tmp_path, run_id, context=RunContext(code_sha="test-sha"))
        ledger.write(
            "reviews",
            {"kind": "titles", "agent": "critic", "release_title": release, "take_titles": takes},
        )
    # Oldest first, deduped, release and take titles both on the shelf.
    assert load_recent_titles(tmp_path) == [
        "Standing Water",
        "Pour Again",
        "Two Thirds Warm",
    ]
    # The current run's own rows never feed its naming call.
    assert load_recent_titles(tmp_path, exclude_run="run-b") == [
        "Standing Water",
        "Pour Again",
    ]
    assert load_recent_titles(tmp_path, limit=1) == ["Two Thirds Warm"]


def test_load_recent_tape_titles_reads_the_vault_shelf(tmp_path: Path):
    ledger = JsonlLedger(tmp_path, "run-a", context=RunContext(code_sha="test-sha"))
    ledger.write(
        "archives",
        {"kind": "shelving", "agent": "archivist", "tape_title": "Mock Session Tape"},
    )
    ledger.write(  # a degraded stage row on the same table never becomes a title
        "archives",
        {"kind": "staff_stage_failed", "agent": "archivist", "stage": "archivist"},
    )
    assert load_recent_tape_titles(tmp_path) == ["Mock Session Tape"]
    assert load_recent_tape_titles(tmp_path, exclude_run="run-a") == []


def test_run_staff_feeds_prior_titles_into_the_naming_call(played_run: Path):
    # A prior run's titles are on the log; run_staff must show them to the namer.
    prior = JsonlLedger(played_run.parent, "prior-run", context=RunContext(code_sha="test-sha"))
    prior.write(
        "reviews",
        {
            "kind": "titles",
            "agent": "critic",
            "release_title": "Standing Water",
            "take_titles": {"silt": "Pour Again"},
        },
    )
    config = _mock_config(played_run.parent)
    run_staff(played_run, config)

    naming_calls = [
        "\n".join(m.content for m in call)
        for call in config.model.calls
        if any("Name it — the last word" in m.content for m in call)
    ]
    assert len(naming_calls) == 1
    assert "Standing Water" in naming_calls[0] and "Pour Again" in naming_calls[0]


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

    # briefs / reactions: the boundary's outward half, one row each.
    (brief_row,) = _rows(run_dir, "briefs")
    assert brief_row["kind"] == "brief" and brief_row["agent"] == "muse"
    assert brief_row["stance"] == "porous"  # the default cycle's first era
    assert brief_row["theme"] and brief_row["text"] and brief_row["carried_forward"] is True
    (reaction_row,) = _rows(run_dir, "reactions")
    assert reaction_row["kind"] == "reaction" and reaction_row["agent"] == "listener"
    assert reaction_row["valence"] in ("loved", "liked", "mixed", "cold")
    assert reaction_row["text"]

    # The supersede CHAIN: base -> producer/critic -> muse/listener -> archivist.
    record = result.release_record
    assert result.released
    assert record["provenance"]["staff"] == ["producer", "critic", "muse", "listener", "archivist"]
    assert record["release_id"] != old_record["release_id"]
    assert result.release_path.exists()
    assert newest_release_path(run_dir) == result.release_path
    assert len(list(run_dir.glob("release-*.json"))) == 4
    ml_id = record["provenance"]["supersedes_release_id"]
    ml_record = json.loads((run_dir / f"release-{ml_id[:12]}.json").read_text())
    assert ml_record["provenance"]["staff"] == ["producer", "critic", "muse", "listener"]
    mid_id = ml_record["provenance"]["supersedes_release_id"]
    mid_path = run_dir / f"release-{mid_id[:12]}.json"
    mid_record = json.loads(mid_path.read_text())
    assert mid_record["provenance"]["staff"] == ["producer", "critic"]
    assert mid_record["provenance"]["supersedes_release_id"] == old_record["release_id"]
    assert brief_row["basis_release_id"] == mid_id  # the Muse read what shipped
    assert reaction_row["basis_release_id"] == mid_id
    # The interaction facts are untouched — staff adds, never edits.
    for key in ("influence", "convergence", "novelty", "asymmetry", "rounds", "artifacts", "set"):
        assert record[key] == old_record[key]
    # The staff block carries the cut, the word, the brief, the reception,
    # and the Archivist's sleeve (liner notes + the tape's place).
    staff = record["staff"]
    assert set(staff) == {"producer", "critic", "muse", "listener", "archivist"}
    assert staff["archivist"]["liner_notes"]
    assert staff["archivist"]["tape"]["placement"] in ("companion", "standalone", "collection")
    (shelving_row,) = [r for r in _rows(run_dir, "archives") if r["kind"] == "shelving"]
    assert shelving_row["agent"] == "archivist"
    assert shelving_row["liner_notes"] == staff["archivist"]["tape"]["notes"]
    assert shelving_row["status"] == "released"
    assert set(staff["producer"]["selected"]) == set(_PLAYERS)
    for pid in _PLAYERS:
        sel = staff["producer"]["selected"][pid]
        assert sel["take_id"] == old_record["artifacts"][sel["round"]][pid]
    assert staff["critic"]["release_title"] == "Mock Pressing"
    assert set(staff["critic"]["act_reviews"]) == set(_PLAYERS)
    assert staff["muse"]["text"] == brief_row["text"]
    assert staff["muse"]["carried_forward"] is True
    assert staff["listener"]["valence"] == reaction_row["valence"]
    assert staff["listener"]["text"] == reaction_row["text"]
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
    assert not (run_dir / "briefs.jsonl").exists()  # nothing shipped: no brief
    assert not (run_dir / "reactions.jsonl").exists()  # …and nothing to hear
    assert len(list(run_dir.glob("release-*.json"))) == 1  # nothing superseded
    # The vault doctrine: the veto stands — and the TAPE SURVIVES. The
    # Archivist still shelved the rejected session, honestly framed.
    archives = _rows(run_dir, "archives")
    (shelving_row,) = [r for r in archives if r["kind"] == "shelving"]
    assert shelving_row["status"] == "rejected"
    assert shelving_row["liner_notes"]
    assert result.shelving is not None


# --- the Muse + Listener half of the frame -------------------------------------


def test_run_muse_listener_requires_a_cut_record(played_run: Path):
    # The outward half acts only AFTER the release exists: on a run whose
    # newest record has no Producer cut, it refuses rather than inventing one.
    config = _mock_config(played_run.parent)
    with pytest.raises(ValueError, match="no Producer cut"):
        run_muse_listener(played_run, config)


def test_run_muse_listener_enriches_an_already_cut_record(played_run: Path):
    # The retrospective path: Producer/Critic have already run (their rows and
    # record exist); the Muse + Listener enrich on top without re-running them.
    config = _mock_config(played_run.parent)
    run_staff(played_run, config)
    selections_before = (played_run / "selections.jsonl").read_text()
    reviews_before = (played_run / "reviews.jsonl").read_text()

    boundary = run_muse_listener(played_run, config)

    # Producer/Critic rows untouched; a second brief/reaction row appended.
    assert (played_run / "selections.jsonl").read_text() == selections_before
    assert (played_run / "reviews.jsonl").read_text() == reviews_before
    assert len(_rows(played_run, "briefs")) == 2
    assert len(_rows(played_run, "reactions")) == 2
    assert boundary.release_record["provenance"]["staff"] == [
        "producer", "critic", "muse", "listener", "archivist", "muse", "listener",
    ]
    assert newest_release_path(played_run) == boundary.release_path


def test_the_reception_loop_reaches_the_next_brief(tmp_path: Path):
    # Run A ships and the Listener reacts; at run B's boundary the Muse must
    # READ that logged reaction — the loop closes at set boundaries, through
    # the log, never the ear.
    config = _mock_config(tmp_path)
    for run_id in ("run-a", "run-b"):
        ledger = JsonlLedger(tmp_path, run_id, context=RunContext(code_sha="test-sha"))
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
    provider = MockProvider(responder=_mock_players)
    config_a = _mock_config(tmp_path, responder=_mock_players)
    run_staff(tmp_path / "run-a", config_a)
    (reaction_row,) = _rows(tmp_path / "run-a", "reactions")

    config_b = AfarConfig(
        model=provider,
        renderer=MockRenderer(tmp_path / "audio"),
        runs_root=tmp_path,
        live=False,
        code_sha="test-sha",
    )
    run_staff(tmp_path / "run-b", config_b)
    muse_calls = [
        "\n".join(m.content for m in call)
        for call in provider.calls
        if any("Write the brief" in m.content for m in call)
    ]
    assert muse_calls, "the Muse never composed at run B's boundary"
    assert reaction_row["text"] in muse_calls[-1]
