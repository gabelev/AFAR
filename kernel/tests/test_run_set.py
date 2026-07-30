"""THE Step B acceptance: three players, four rounds, offline, end to end.

MockProvider + MockRenderer + MockEmbedder: a full set produces every Step B
table, features in both spaces, and a release record whose content hash is
reproducible from (personas, condition, rounds, seed) alone.
"""

import json
from pathlib import Path

from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.run import run_set

_PLAYERS = ("silt", "rust", "keep")
_ROUNDS = 4
_STEP_B_TABLES = (
    "runs",
    "sets",
    "rounds",
    "perceptions",
    "intents",
    "artifacts",
    "embeddings",
    "features",
    "releases",
)


def _run(tmp_path: Path, *, name: str = "one", condition: str = "contact", seed: int = 11):
    root = tmp_path / name
    renderer = MockRenderer(root / "audio")
    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=renderer,
        runs_root=root,
        live=False,
        code_sha="test-sha",
    )
    ledger = JsonlLedger(root, f"{name}-run", context=RunContext(code_sha="test-sha"))
    players = [Player(PERSONAS[pid], config.model, renderer) for pid in _PLAYERS]
    result = run_set(
        players,
        rounds=_ROUNDS,
        condition=condition,
        config=config,
        ledger=ledger,
        embedder=MockEmbedder(),
        seed=seed,
    )
    return result, ledger


def _rows(ledger: JsonlLedger, table: str) -> list[dict]:
    path = ledger.run_dir / f"{table}.jsonl"
    assert path.exists(), f"missing {table}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_mock_set_populates_every_step_b_table(tmp_path: Path):
    _, ledger = _run(tmp_path)
    for table in _STEP_B_TABLES:
        assert _rows(ledger, table), f"{table} is empty"
    assert len(_rows(ledger, "perceptions")) == len(_PLAYERS) * _ROUNDS
    assert len(_rows(ledger, "intents")) == len(_PLAYERS) * _ROUNDS
    assert len(_rows(ledger, "artifacts")) == len(_PLAYERS) * _ROUNDS
    assert len(_rows(ledger, "rounds")) == _ROUNDS
    # Two embeddings per (player, round): one per space.
    assert len(_rows(ledger, "embeddings")) == len(_PLAYERS) * _ROUNDS * 2


def test_embeddings_rows_carry_space_model_and_version(tmp_path: Path):
    _, ledger = _run(tmp_path)
    rows = _rows(ledger, "embeddings")
    by_space = {"audio": [], "intent": []}
    for row in rows:
        by_space[row["space"]].append(row)
    for row in by_space["audio"]:
        assert row["model_id"] == "mock"
        assert row["dim"] == 16
        assert len(row["vector"]) == 16
        assert row["artifact_id"]
    for row in by_space["intent"]:
        assert row["model_id"] == "intent-vector"
        assert row["dim"] == 18
        assert row["intent_vector_version"] == "1"
        assert row["intent_id"]


def test_features_rows_exist_in_both_spaces(tmp_path: Path):
    _, ledger = _run(tmp_path)
    rows = _rows(ledger, "features")
    assert {row["space"] for row in rows} == {"audio", "intent"}
    for space in ("audio", "intent"):
        kinds = {row["feature"] for row in rows if row["space"] == space}
        assert kinds == {"influence", "convergence", "novelty", "asymmetry"}


def test_release_record_hash_is_stable_across_identical_runs(tmp_path: Path):
    one, _ = _run(tmp_path, name="one")
    two, _ = _run(tmp_path, name="two")
    assert one.release_record["release_id"] == two.release_record["release_id"]
    assert one.release_record == two.release_record


def test_release_record_is_logged_and_written_to_disk(tmp_path: Path):
    result, ledger = _run(tmp_path)
    record = result.release_record
    assert result.paths["release"].exists()
    assert json.loads(result.paths["release"].read_text()) == record
    (release_row,) = _rows(ledger, "releases")
    assert release_row["id"] == record["release_id"]
    assert release_row["record"] == record
    # The record carries the whole interaction: per-round lines + lyrics +
    # rationales and content-addressed artifact hashes for every player.
    assert len(record["rounds"]) == _ROUNDS
    assert len(record["artifacts"]) == _ROUNDS
    for frames, hashes in zip(record["rounds"], record["artifacts"]):
        assert set(frames) == set(_PLAYERS)
        assert set(hashes) == set(_PLAYERS)
        for pid in _PLAYERS:
            assert frames[pid]["line"]
            assert frames[pid]["lyrics"]
            assert frames[pid]["rationale"]
    artifact_hashes = {row["hash"] for row in _rows(ledger, "artifacts")}
    assert {h for hashes in record["artifacts"] for h in hashes.values()} <= artifact_hashes


def test_parallel_condition_logs_empty_others_in_every_perception(tmp_path: Path):
    _, ledger = _run(tmp_path, condition="parallel")
    rows = _rows(ledger, "perceptions")
    assert len(rows) == len(_PLAYERS) * _ROUNDS
    for row in rows:
        assert row["context"]["others"] == []


def test_contact_perceptions_hear_the_other_two_from_round_one_on(tmp_path: Path):
    _, ledger = _run(tmp_path, condition="contact")
    for row in _rows(ledger, "perceptions"):
        heard = {entry["player_id"] for entry in row["context"]["others"]}
        if row["round"] == 0:
            assert heard == set()
        else:
            assert heard == set(_PLAYERS) - {row["player"]}
