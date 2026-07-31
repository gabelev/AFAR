"""THE Step A acceptance: one player makes one track, offline, end to end.

MockProvider (persona-keyed responder) + MockRenderer + JsonlLedger:
Intent -> mapping -> renderer -> file on disk + log rows, with full
provenance on every row. If this passes, the vertical slice stands.
"""

import hashlib
import json
from pathlib import Path

import pytest

from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player, render_one
from afar.config import _MOCK_INTENTS, _mock_players
from afar.intent import Influence, Intent, SonicPalette, VocalCharacter
from afar.log import JsonlLedger, RunContext
from afar.mapping import LYRIC_LINE_MAX_CHARS, TRACK_DURATION_MS, clamp_lyrics
from afar.render.base import MockRenderer

_STAMPS = ("condition", "code_sha", "seed", "renderer_version", "prompt_sha")


@pytest.fixture
def run(tmp_path: Path):
    player = Player(PERSONAS["silt"], MockProvider(responder=_mock_players), MockRenderer(tmp_path / "audio"))
    ledger = JsonlLedger(tmp_path / "runs", "test-run", context=RunContext(code_sha="test-sha"))
    artifact = render_one(player, {}, ledger, seed=7, condition="baseline")
    return artifact, ledger


def _rows(ledger: JsonlLedger, table: str) -> list[dict]:
    path = ledger.run_dir / f"{table}.jsonl"
    assert path.exists(), f"missing {table}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_decision_yields_a_valid_persona_true_intent(run):
    artifact, ledger = run
    (intent_row,) = _rows(ledger, "intents")
    intent = Intent.from_json(
        json.dumps(
            dict(
                intent_row["intent"],
                line=intent_row["line"],
                lyrics=intent_row["lyrics"],
                rationale=intent_row["rationale"],
                player_id=intent_row["player"],
            )
        )
    )
    intent.validate()
    assert intent.player_id == "silt"
    assert intent.line.strip()
    assert intent.lyrics.strip()
    assert intent.rationale.strip()


def test_composition_plan_has_exactly_one_30s_chunk(run):
    artifact, _ = run
    plan = artifact.metadata["render"]["composition_plan"]
    assert len(plan["chunks"]) == 1
    assert plan["chunks"][0]["duration_ms"] == TRACK_DURATION_MS


def test_chunk_text_is_the_sung_lyrics_not_the_spoken_line(run):
    # The vocals regression: chunk text must come from intent.lyrics, clamped,
    # never from the one-sentence chat-bubble line.
    artifact, _ = run
    text = artifact.metadata["render"]["composition_plan"]["chunks"][0]["text"]
    silt = _MOCK_INTENTS["silt"]
    assert text == clamp_lyrics(silt["lyrics"])
    assert text != silt["line"]


def test_long_lyrics_are_clamped_to_the_api_limit_at_render_time(tmp_path: Path):
    long_lyrics = " ".join(["sediment settles"] * 30)  # well over 180 chars
    intent = Intent(
        seedPrompt="test artist",
        era=7,
        influences=(
            Influence("drone", 0.4),
            Influence("dub", 0.3),
            Influence("spiritual jazz", 0.2),
            Influence("tape music", 0.1),
        ),
        sonicPalette=SonicPalette(0, 0, 0, 0, 0, 0, 0),
        vocalCharacter=VocalCharacter(0, 0),
        lyricalObsessions=("sediment",),
        visualStyle=("amber",),
        line="A short spoken line.",
        lyrics=long_lyrics,
        rationale="test",
        player_id="silt",
    ).validate()
    result = MockRenderer(tmp_path / "audio").render(intent, seed=1)
    text = result.metadata["composition_plan"]["chunks"][0]["text"]
    assert text == clamp_lyrics(long_lyrics)
    assert all(len(line) <= LYRIC_LINE_MAX_CHARS for line in text.split("\n"))
    assert text.startswith("sediment settles")
    assert text != intent.line


def test_track_file_exists_and_its_sha256_matches_the_artifacts_row(run):
    artifact, ledger = run
    path = Path(artifact.body)
    assert path.exists()
    file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    (artifact_row,) = _rows(ledger, "artifacts")
    assert artifact_row["hash"] == file_sha
    assert artifact_row["id"] == file_sha  # content-addressed
    assert artifact_row["path"] == str(path)


def test_every_logged_row_carries_full_provenance(run):
    _, ledger = run
    for table in ("perceptions", "intents", "artifacts"):
        (row,) = _rows(ledger, table)
        for stamp in _STAMPS:
            assert stamp in row, f"{table} row missing {stamp}"
        assert row["condition"] == "baseline"
        assert row["code_sha"] == "test-sha"
        assert row["seed"] == 7
        assert row["renderer_version"] == "mock"
        assert row["prompt_sha"]
        assert row["run_id"] == "test-run"
        assert row["ts"]


def test_intents_row_links_to_the_artifact(run):
    _, ledger = run
    (intent_row,) = _rows(ledger, "intents")
    (artifact_row,) = _rows(ledger, "artifacts")
    assert artifact_row["intent_id"] == intent_row["id"]
    assert artifact_row["kind"] == "track"


def test_same_intent_and_seed_render_identical_bytes(tmp_path: Path):
    # Content addressing only means anything if the mock is truly deterministic.
    renderer_a = MockRenderer(tmp_path / "a")
    renderer_b = MockRenderer(tmp_path / "b")
    provider = MockProvider(responder=_mock_players)
    player_a = Player(PERSONAS["silt"], provider, renderer_a)
    player_b = Player(PERSONAS["silt"], provider, renderer_b)
    ledger_a = JsonlLedger(tmp_path / "runs", "a", context=RunContext(code_sha="x"))
    ledger_b = JsonlLedger(tmp_path / "runs", "b", context=RunContext(code_sha="x"))
    one = render_one(player_a, {}, ledger_a, seed=3, condition="c")
    two = render_one(player_b, {}, ledger_b, seed=3, condition="c")
    assert one.metadata["content_hash"] == two.metadata["content_hash"]
    assert Path(one.body).read_bytes() == Path(two.body).read_bytes()
