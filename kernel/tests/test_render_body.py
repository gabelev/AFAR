"""Request-body oracles, ported from afar_music's music.test.ts.

music_v2 reads style direction and context_adherence from the plan's CHUNKS;
the body must carry ONLY model_id + composition_plan. Anything else (top-level
context_adherence, respect_sections_durations) is silently ignored by the API —
which is exactly how every early AFAR track lost its palette.
"""

import json
from pathlib import Path

from afar.intent import Influence, Intent, SonicPalette, VocalCharacter
from afar.render.base import MockRenderer
from afar.render.elevenlabs import ElevenLabsRenderer


def _intent() -> Intent:
    return Intent(
        seedPrompt="test artist",
        era=8,
        influences=(
            Influence("folk", 0.4),
            Influence("americana", 0.3),
            Influence("chamber pop", 0.2),
            Influence("ambient", 0.1),
        ),
        sonicPalette=SonicPalette(0, 0, 0, -1, 0, 0, 0),
        vocalCharacter=VocalCharacter(0, 0),
        lyricalObsessions=("rain",),
        visualStyle=("neon fog",),
        line="A short spoken line.",
        lyrics="rain keeps its own time",
        rationale="test",
        player_id="silt",
    ).validate()


def test_elevenlabs_posts_a_body_whose_only_keys_are_model_id_and_composition_plan(
    tmp_path: Path, monkeypatch
):
    # Regression: the body used to carry top-level context_adherence and
    # respect_sections_durations — the first is a per-chunk field, the second
    # is music_v1-only; both were silently ignored by the API.
    renderer = ElevenLabsRenderer("test-key", tmp_path / "audio")
    captured: dict[str, bytes] = {}

    def fake_post(body: bytes):
        captured["body"] = body
        return b"\x01\x02\x03", {"x-song-id": "song-123"}

    monkeypatch.setattr(renderer, "_post", fake_post)
    result = renderer.render(_intent(), seed=7)

    body = json.loads(captured["body"])
    assert sorted(body) == ["composition_plan", "model_id"]
    assert body["model_id"] == "music_v2"
    assert result.metadata["x-song-id"] == "song-123"

    chunk = body["composition_plan"]["chunks"][0]
    assert chunk["context_adherence"] == "low"  # improvisedStructured -1
    assert chunk["positive_styles"]  # styles ride ON the chunk, where v2 reads them
    assert set(body["composition_plan"]) == {"chunks"}


def test_mock_renderer_hashes_the_same_body_shape_as_the_live_one(tmp_path: Path):
    # prompt_sha must mean the same thing across renderers: a hash of a
    # {model_id, composition_plan} payload, nothing more.
    result = MockRenderer(tmp_path / "audio").render(_intent(), seed=7)
    plan = result.metadata["composition_plan"]
    assert set(plan) == {"chunks"}
    chunk = plan["chunks"][0]
    assert chunk["positive_styles"]
    assert chunk["context_adherence"] == "low"
