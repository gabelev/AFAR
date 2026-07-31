"""The append-only correction path and the guard that makes it unnecessary.

Offline end to end: a mock set is played (MockProvider + MockRenderer +
MockEmbedder), then re-embedded with a fake "real" embedder. The re-embed
must APPEND — new embeddings rows, new features rows, a second release
record — and never touch the original rows, the intent space, or the old
release file. Plus the step_b guard: a live renderer with the mock embedder
is refused unless explicitly allowed.
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.run import run_set

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: @dataclass resolves types via sys.modules[__module__].
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reembed = _load_script("reembed")
step_b = _load_script("step_b")

_PLAYERS = ("silt", "rust", "keep")
_ROUNDS = 4
_RUN_ID = "test-run"


class FakeMert:
    """Stands in for MERT in the mechanics test: deterministic, offline, and
    guaranteed to disagree with MockEmbedder so the corrected features move."""

    name = "fake-mert"
    dim = 4

    def embed(self, path: Path) -> list[float]:
        digest = hashlib.sha256(path.read_bytes()).digest()
        return [b / 255.0 for b in digest[: self.dim]]


@pytest.fixture
def played_run(tmp_path: Path) -> Path:
    """One full mock set logged under tmp_path/<_RUN_ID>; returns the runs root."""
    renderer = MockRenderer(tmp_path / "audio")
    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=renderer,
        runs_root=tmp_path,
        live=False,
        code_sha="test-sha",
    )
    ledger = JsonlLedger(tmp_path, _RUN_ID, context=RunContext(code_sha="test-sha"))
    players = [Player(PERSONAS[pid], config.model, renderer) for pid in _PLAYERS]
    run_set(
        players,
        rounds=_ROUNDS,
        condition="contact",
        config=config,
        ledger=ledger,
        embedder=MockEmbedder(),
        seed=11,
    )
    return tmp_path


def _rows(runs_root: Path, table: str) -> list[dict]:
    path = runs_root / _RUN_ID / f"{table}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_reembed_appends_new_audio_rows_and_never_edits(played_run: Path):
    run_dir = played_run / _RUN_ID
    emb_before = (run_dir / "embeddings.jsonl").read_text()
    feat_before = (run_dir / "features.jsonl").read_text()
    old_release = reembed.newest_release_path(run_dir)
    old_bytes = old_release.read_text()

    result = reembed.reembed_run(played_run, _RUN_ID, FakeMert())

    # Strictly appended: the old bytes are a prefix of the new files.
    assert (run_dir / "embeddings.jsonl").read_text().startswith(emb_before)
    assert (run_dir / "features.jsonl").read_text().startswith(feat_before)
    assert old_release.read_text() == old_bytes  # old record kept, untouched

    new_embeddings = [
        row for row in _rows(played_run, "embeddings") if row["model_id"] == "fake-mert"
    ]
    assert len(new_embeddings) == len(_PLAYERS) * _ROUNDS
    for row in new_embeddings:
        assert row["space"] == "audio"
        assert row["dim"] == FakeMert.dim
        assert len(row["vector"]) == FakeMert.dim
        assert row["artifact_id"]
        assert "supersedes 'mock'" in row["note"]
        # Provenance stamps carried over from the artifact row being re-read.
        assert row["renderer_version"] and row["prompt_sha"]

    new_features = [
        row for row in _rows(played_run, "features") if row.get("model_id") == "fake-mert"
    ]
    assert {row["space"] for row in new_features} == {"audio"}
    assert {row["feature"] for row in new_features} == {
        "influence", "convergence", "novelty", "asymmetry",
    }
    # influence: rounds-1; asymmetry: 3 pairs * (rounds-1); convergence: rounds;
    # novelty: 3 players * (rounds-1).
    assert len(new_features) == (_ROUNDS - 1) + 3 * (_ROUNDS - 1) + _ROUNDS + 3 * (_ROUNDS - 1)
    assert result.embeddings_by_player.keys() == set(_PLAYERS)


def test_reembed_writes_a_new_release_record_with_provenance(played_run: Path):
    run_dir = played_run / _RUN_ID
    old_record = json.loads(reembed.newest_release_path(run_dir).read_text())

    result = reembed.reembed_run(played_run, _RUN_ID, FakeMert())
    record = result.release_record

    assert result.release_path.exists()
    assert result.release_path.name == f"release-{record['release_id'][:12]}.json"
    assert len(list(run_dir.glob("release-*.json"))) == 2  # old file kept
    assert record["release_id"] != old_record["release_id"]
    assert record["provenance"] == {
        "audio_reembedded_from": "mock",
        "embedder": "fake-mert",
        "supersedes_release_id": old_record["release_id"],
    }
    assert record["set"]["embedder"] == {"name": "fake-mert", "dim": FakeMert.dim}
    # Audio space corrected, intent space untouched, frames/artifacts untouched.
    assert record["influence"]["audio"] != old_record["influence"]["audio"]
    assert record["convergence"]["audio"] != old_record["convergence"]["audio"]
    assert record["influence"]["intent"] == old_record["influence"]["intent"]
    assert record["convergence"]["intent"] == old_record["convergence"]["intent"]
    assert record["novelty"]["intent"] == old_record["novelty"]["intent"]
    assert record["asymmetry"]["intent"] == old_record["asymmetry"]["intent"]
    assert record["rounds"] == old_record["rounds"]
    assert record["artifacts"] == old_record["artifacts"]
    # Logged as a second releases row; the newest release file is the corrected one.
    releases = _rows(played_run, "releases")
    assert [row["id"] for row in releases] == [old_record["release_id"], record["release_id"]]
    assert reembed.newest_release_path(run_dir) == result.release_path


def test_reembed_refuses_a_run_already_on_the_same_embedder(played_run: Path):
    reembed.reembed_run(played_run, _RUN_ID, FakeMert())
    with pytest.raises(ValueError, match="already embedded"):
        reembed.reembed_run(played_run, _RUN_ID, FakeMert())


def test_guard_refuses_live_renderer_with_mock_embedder():
    with pytest.raises(SystemExit, match="refusing to run live renderer"):
        step_b.ensure_real_ears_for_live_renders(
            "elevenlabs", "mock", allow_mock_embedder=False
        )


@pytest.mark.parametrize(
    "renderer,embedder,allow",
    [
        ("elevenlabs", "mock", True),   # explicit override
        ("elevenlabs", "mert", False),  # real ears on a live render
        ("mock", "mock", False),        # fully offline wiring check
    ],
)
def test_guard_permits_honest_combinations(renderer: str, embedder: str, allow: bool):
    step_b.ensure_real_ears_for_live_renders(renderer, embedder, allow_mock_embedder=allow)
