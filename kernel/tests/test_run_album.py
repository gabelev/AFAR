"""THE acceptance for the new spine: one artist, one record, start to finish.

MockProvider + MockRenderer + MockEmbedder, no network: an album is written,
every track is rendered from its own DNA, both spaces are embedded, the
album-cadence features are computed against what the artist heard, and every
one of it lands in the append-only log.
"""

from __future__ import annotations

import json
from pathlib import Path

from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import AfarConfig, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.perception.album_context import Ears, HeardAlbum, HeardTrack
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.run import measure_heard_albums, run_album, track_seed

_ALBUM_TABLES = ("runs", "albums", "perceptions", "intents", "artifacts", "embeddings", "features")


def _heard(tmp_path: Path, *, with_audio: bool = False) -> tuple[tuple[HeardAlbum, ...], Ears]:
    """One record by another artist, with the runner-side measurements the
    conductor would have read back out of the log."""
    album = HeardAlbum(
        artist_id="rust",
        title="Oxide in the Joist",
        description="Four takes left outdoors for a season.",
        tracks=(
            HeardTrack(title="Standpipe", note="I kept the hiss.", content_hash="h1"),
            HeardTrack(title="Sill Water", note="Cut the second bar.", content_hash="h2"),
        ),
        artist_name="Roan Patina",
        album_id="AFAR-0002",
    )
    audio: dict[str, Path] = {}
    if with_audio:
        for digest in ("h1", "h2"):
            path = tmp_path / f"{digest}.mp3"
            path.write_bytes(b"afar-mock-track\n" + digest.encode() * 64)
            audio[digest] = path
    # Deliberately non-uniform: every uniform vector is cosine-identical to
    # every other, which would make every relation read as "no movement".
    def _vec(dim: int, offset: int) -> list[float]:
        return [((i * 7 + offset) % 13) / 13.0 for i in range(dim)]

    ears = Ears(
        audio=audio,
        vectors={
            "audio": {"h1": _vec(16, 1), "h2": _vec(16, 2)},
            "intent": {"h1": _vec(18, 3), "h2": _vec(18, 4)},
        },
        # two records of their own history: enough for novelty AND for the
        # ear's "did they move toward you or away" sign.
        own_past={
            "audio": [_vec(16, 5), _vec(16, 6)],
            "intent": [_vec(18, 7), _vec(18, 8)],
        },
        maker_past={"audio": {"rust": _vec(16, 9)}},
    )
    return (album,), ears


def _run(tmp_path: Path, *, name: str = "one", seed: int = 11, n_tracks: int = 3, **over):
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
    player = Player(PERSONAS["silt"], config.model, renderer)
    heard, ears = _heard(tmp_path)
    kwargs = dict(heard=heard, ears=ears)
    kwargs.update(over)
    result = run_album(
        player,
        n_tracks=n_tracks,
        duration_s=45,
        config=config,
        ledger=ledger,
        embedder=MockEmbedder(),
        seed=seed,
        **kwargs,
    )
    return result, ledger


def _rows(ledger: JsonlLedger, table: str) -> list[dict]:
    path = ledger.run_dir / f"{table}.jsonl"
    assert path.exists(), f"missing {table}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- the record ----------------------------------------------------------------


def test_one_album_populates_every_table(tmp_path: Path):
    result, ledger = _run(tmp_path)
    for table in _ALBUM_TABLES:
        assert _rows(ledger, table), f"{table} is empty"
    assert len(_rows(ledger, "intents")) == 3
    assert len(_rows(ledger, "artifacts")) == 3
    assert len(_rows(ledger, "embeddings")) == 6  # two spaces per track
    assert len(_rows(ledger, "perceptions")) == 1  # one hearing per record
    assert len(_rows(ledger, "albums")) == 1
    assert len(result.tracks) == 3


def test_every_track_is_rendered_and_content_addressed(tmp_path: Path):
    result, ledger = _run(tmp_path)
    hashes = {row["hash"] for row in _rows(ledger, "artifacts")}
    assert len(hashes) == 3
    for track in result.tracks:
        assert track.audio_path.exists()
        assert track.content_hash in hashes
        assert track.intent.lyrics
        assert track.title and track.note


def test_track_seeds_are_derived_per_track_and_never_collide(tmp_path: Path):
    result, _ = _run(tmp_path)
    seeds = [t.seed for t in result.tracks]
    assert len(set(seeds)) == 3
    for i, track in enumerate(result.tracks):
        assert track.seed == track_seed(11, "silt", result.album_id, i)


def test_two_albums_by_the_same_artist_on_one_seed_do_not_share_audio(tmp_path: Path):
    a = track_seed(11, "silt", "album-a", 0)
    b = track_seed(11, "silt", "album-b", 0)
    assert a != b


def test_the_logged_context_is_what_the_artist_saw(tmp_path: Path):
    _, ledger = _run(tmp_path)
    (row,) = _rows(ledger, "perceptions")
    assert row["player"] == "silt"
    assert row["context"]["heard"][0]["title"] == "Oxide in the Joist"
    assert row["context"]["isolated"] is False


def test_the_album_row_carries_the_whole_sleeve(tmp_path: Path):
    result, ledger = _run(tmp_path)
    (row,) = _rows(ledger, "albums")
    assert row["id"] == result.album_id
    assert row["record"] == result.record
    album = row["record"]["album"]
    assert album["title"] == result.album.title
    assert album["description"]
    assert len(album["tracks"]) == 3
    for track in album["tracks"]:
        assert track["title"] and track["lyrics"] and track["intent"]


def test_the_record_is_written_to_disk_and_reproducible(tmp_path: Path):
    one, _ = _run(tmp_path, name="one")
    two, _ = _run(tmp_path, name="two")
    assert one.paths["record"].exists()
    assert json.loads(one.paths["record"].read_text()) == one.record
    assert one.record["record_id"] == two.record["record_id"]
    assert one.album_id == two.album_id
    # ... and the same record hash means the same audio, byte for byte.
    assert [t.content_hash for t in one.tracks] == [t.content_hash for t in two.tracks]


def test_the_record_names_what_it_heard(tmp_path: Path):
    result, _ = _run(tmp_path)
    assert result.record["heard"] == [
        {"album_id": "AFAR-0002", "artist_id": "rust", "title": "Oxide in the Joist"}
    ]


def test_a_debut_hears_nothing_and_still_makes_a_record(tmp_path: Path):
    result, ledger = _run(tmp_path, heard=(), ears=Ears())
    assert len(result.tracks) == 3
    (row,) = _rows(ledger, "perceptions")
    assert row["context"]["heard"] == []
    for space in ("audio", "intent"):
        assert result.features[space]["influence"] == {}
        assert result.features[space]["novelty"] == 0.0


def test_the_isolation_control_hears_no_one(tmp_path: Path):
    result, ledger = _run(tmp_path, isolated=True)
    (row,) = _rows(ledger, "perceptions")
    assert row["context"]["heard"] == []
    assert "Oxide in the Joist" not in json.dumps(row["context"])
    assert result.record["session"]["isolated"] is True


# --- features at album cadence -------------------------------------------------


def test_features_are_computed_and_logged_in_both_spaces(tmp_path: Path):
    result, ledger = _run(tmp_path)
    rows = _rows(ledger, "features")
    assert {row["space"] for row in rows} == {"audio", "intent"}
    assert {row["cadence"] for row in rows} == {"album"}
    for space in ("audio", "intent"):
        kinds = {row["feature"] for row in rows if row["space"] == space}
        assert kinds == {"influence", "convergence", "novelty"}
        block = result.features[space]
        assert set(block["influence"]) == {"AFAR-0002"}
        assert isinstance(block["convergence"], float)
        assert isinstance(block["novelty"], float)
    influence_rows = [r for r in rows if r["feature"] == "influence"]
    assert {r["from_album"] for r in influence_rows} == {"AFAR-0002"}


def test_logged_feature_values_match_the_returned_block(tmp_path: Path):
    result, ledger = _run(tmp_path)
    for row in _rows(ledger, "features"):
        block = result.features[row["space"]]
        if row["feature"] == "influence":
            assert row["value"] == block["influence"][row["from_album"]]
        else:
            assert row["value"] == block[row["feature"]]


def test_an_album_with_no_logged_vectors_is_not_an_influence_edge(tmp_path: Path):
    album = HeardAlbum(
        artist_id="keep",
        title="A Door Left Open",
        description="d",
        tracks=(HeardTrack(title="Four Chords", note="n", content_hash="unlogged"),),
        album_id="AFAR-0003",
    )
    heard, ears = _heard(tmp_path)
    result, _ = _run(tmp_path, heard=(*heard, album), ears=ears)
    assert set(result.features["audio"]["influence"]) == {"AFAR-0002"}


# --- the ear pass --------------------------------------------------------------


def test_tracks_with_audio_and_vectors_get_measured(tmp_path: Path):
    heard, ears = _heard(tmp_path, with_audio=True)
    (measured,) = measure_heard_albums(heard, ears)
    for track in measured.tracks:
        assert track.heard is not None
        # DSP is optional equipment (librosa may be absent, and mock bytes are
        # not audio) — the relations always carry the dict.
        assert track.heard["distance_to_yours"] is not None
        assert track.heard["distance_to_their_last"] is not None


def test_a_track_with_no_logged_vector_was_never_heard(tmp_path: Path):
    heard, ears = _heard(tmp_path)
    thinned = Ears(
        audio=ears.audio,
        vectors={"audio": {"h1": [0.1] * 16}, "intent": ears.space("intent")},
        own_past=ears.own_past,
        maker_past=ears.maker_past,
    )
    (measured,) = measure_heard_albums(heard, thinned)
    assert measured.tracks[0].heard is not None
    assert measured.tracks[1].heard is None


def test_measurement_degrades_to_nothing_when_the_runner_measured_nothing(tmp_path: Path):
    heard, _ = _heard(tmp_path)
    assert measure_heard_albums(heard, Ears()) == heard


def test_the_measured_facts_reach_the_prompt(tmp_path: Path):
    root = tmp_path / "measured"
    renderer = MockRenderer(root / "audio")
    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=renderer,
        runs_root=root,
        live=False,
        code_sha="test-sha",
    )
    ledger = JsonlLedger(root, "measured-run", context=RunContext(code_sha="test-sha"))
    player = Player(PERSONAS["silt"], config.model, renderer)
    heard, ears = _heard(tmp_path, with_audio=True)
    run_album(
        player,
        n_tracks=2,
        duration_s=30,
        config=config,
        ledger=ledger,
        embedder=MockEmbedder(),
        seed=3,
        heard=heard,
        ears=ears,
    )
    prompt = player.model.calls[0][1].content
    assert "how it sounded to you:" in prompt
    # measured, not claimed: the sleeve's own words are there too
    assert "I kept the hiss." in prompt


def test_the_runs_row_says_what_kind_of_work_this_was(tmp_path: Path):
    _, ledger = _run(tmp_path)
    (row,) = _rows(ledger, "runs")
    assert row["kind"] == "album"
    assert row["artist"] == "silt"
    assert row["n_tracks"] == 3
    assert row["duration_s"] == 45
    assert row["renderer"] == "mock"
