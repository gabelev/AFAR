"""Variable-length takes (Round 2, Workstream A).

The parity bar: at the 30s default everything is byte-identical to the
single-chunk era — the untouched oracle suite in test_mapping.py proves the
default, these tests prove the new surface. Longer takes: 2-4 sections with
the lyric distributed in order, per-chunk 7/4 style budgets, a line budget
derived from duration (~8 lines/30s, capped at 24), and duration passthrough
all the way down the renderer seam (timeout scaling, mock bytes scaling).
"""

import json
from pathlib import Path

import pytest

from afar.intent import ERAS, Influence, Intent, SonicPalette, VocalCharacter
from afar.mapping import (
    LYRIC_MAX_LINES,
    LYRIC_MAX_LINES_CAP,
    NEGATIVE_STYLE_BUDGET,
    POSITIVE_STYLE_BUDGET,
    SINGLE_CHUNK_MAX_MS,
    TRACK_DURATION_MS,
    build_composition_plan,
    lyric_line_budget,
    section_count,
)

_SNAPSHOTS = Path(__file__).parent / "snapshots"

_NEUTRAL = dict.fromkeys(
    (
        "pristineLofi",
        "sparseDense",
        "coldWarm",
        "improvisedStructured",
        "loudQuiet",
        "organicSynthetic",
        "darkHopeful",
    ),
    0,
)


def _intent(**overrides) -> Intent:
    base = dict(
        seedPrompt="test artist",
        era=ERAS.index("2020s"),
        influences=(
            Influence("synthpop", 0.4),
            Influence("shoegaze", 0.3),
            Influence("trip-hop", 0.2),
            Influence("ambient", 0.1),
        ),
        sonicPalette=SonicPalette(**_NEUTRAL),
        vocalCharacter=VocalCharacter(0, 0),
        lyricalObsessions=("rain",),
        visualStyle=("neon fog",),
        line="x",
        lyrics="rain keeps its own time",
        rationale="test",
        player_id="silt",
    )
    base.update(overrides)
    return Intent(**base)


def _snapshot_intent() -> Intent:
    """The exact intent the committed snapshots were generated from."""
    return _intent(
        seedPrompt="snapshot artist",
        sonicPalette=SonicPalette(0.5, -0.5, 0, 0.7, 0, 0.3, -0.2),
        vocalCharacter=VocalCharacter(0.6, 0),
        lyrics=_long_lyrics(),
        rationale="snapshot",
    ).validate()


def _long_lyrics(lines: int = 30) -> str:
    return "\n".join(f"line {i:02d} of the long take" for i in range(1, lines + 1))


# --- oracle parity at the default ---------------------------------------------


def test_the_default_plan_is_identical_with_and_without_duration():
    lyrics = "rain keeps its own time\nwires hum in the dark"
    a = build_composition_plan(_intent(), lyrics)
    b = build_composition_plan(_intent(), lyrics, duration_ms=TRACK_DURATION_MS)
    assert json.dumps(a.plan, sort_keys=True) == json.dumps(b.plan, sort_keys=True)
    assert a.provenance == b.provenance
    assert a.context_adherence == b.context_adherence


def test_up_to_45s_stays_one_chunk_carrying_the_whole_lyric():
    built = build_composition_plan(_intent(), _long_lyrics(), duration_ms=SINGLE_CHUNK_MAX_MS)
    assert len(built.plan["chunks"]) == 1
    chunk = built.plan["chunks"][0]
    assert chunk["duration_ms"] == SINGLE_CHUNK_MAX_MS
    # The line budget still derives from duration: 45s -> 12 lines.
    assert len(chunk["text"].split("\n")) == lyric_line_budget(SINGLE_CHUNK_MAX_MS) == 12


def test_rejects_a_nonpositive_duration():
    with pytest.raises(ValueError, match="duration_ms"):
        build_composition_plan(_intent(), "x", duration_ms=0)


# --- the derived line budget ---------------------------------------------------


def test_lyric_line_budget_scales_with_duration_and_caps_at_24():
    assert lyric_line_budget(30_000) == LYRIC_MAX_LINES  # the untouched default
    assert lyric_line_budget(60_000) == 16
    assert lyric_line_budget(90_000) == 24
    assert lyric_line_budget(120_000) == LYRIC_MAX_LINES_CAP == 24


def test_section_count_bands():
    assert section_count(46_000) == 2
    assert section_count(60_000) == 2
    assert section_count(61_000) == 3
    assert section_count(90_000) == 3
    assert section_count(91_000) == 4
    assert section_count(120_000) == 4


# --- multi-section plans --------------------------------------------------------


@pytest.mark.parametrize("seconds", [60, 90, 120])
def test_multi_section_plan_matches_the_committed_snapshot(seconds):
    built = build_composition_plan(
        _snapshot_intent(), _long_lyrics(), duration_ms=seconds * 1000
    )
    snapshot = json.loads((_SNAPSHOTS / f"plan_{seconds}s.json").read_text())
    assert built.plan == snapshot


@pytest.mark.parametrize("duration_ms", [46_000, 60_000, 70_000, 90_000, 100_000, 119_000, 120_000])
def test_section_durations_sum_exactly_and_budgets_hold_per_chunk(duration_ms):
    built = build_composition_plan(_intent(), _long_lyrics(), duration_ms=duration_ms)
    chunks = built.plan["chunks"]
    assert 2 <= len(chunks) <= 4
    assert sum(c["duration_ms"] for c in chunks) == duration_ms
    for c in chunks:
        assert len(c["positive_styles"]) <= POSITIVE_STYLE_BUDGET
        assert len(c["negative_styles"]) <= NEGATIVE_STYLE_BUDGET
        assert c["context_adherence"] == built.context_adherence


def test_lyrics_distribute_across_chunks_contiguously_and_in_order():
    built = build_composition_plan(_intent(), _long_lyrics(), duration_ms=120_000)
    chunks = built.plan["chunks"]
    all_lines = [line for c in chunks for line in c["text"].split("\n") if line]
    # 120s -> a 24-line budget, split 6/6/6/6 across 4 sections, in lyric order.
    assert all_lines == _long_lyrics().split("\n")[:24]
    assert [len(c["text"].split("\n")) for c in chunks] == [6, 6, 6, 6]


def test_a_short_lyric_on_a_long_take_leaves_early_sections_instrumental():
    built = build_composition_plan(_intent(), "one line only", duration_ms=120_000)
    texts = [c["text"] for c in built.plan["chunks"]]
    assert texts.count("") == 3
    assert texts[-1] == "one line only"  # contiguous split puts the tail last


# --- renderer duration passthrough ----------------------------------------------


def test_mock_renderer_bytes_scale_with_duration_and_default_is_unchanged(tmp_path: Path):
    from afar.render.base import MockRenderer

    intent = _intent().validate()
    default = MockRenderer(tmp_path / "a").render(intent, seed=1)
    thirty = MockRenderer(tmp_path / "b").render(intent, seed=1, duration_s=30)
    sixty = MockRenderer(tmp_path / "c").render(intent, seed=1, duration_s=60)
    assert Path(default.path).read_bytes() == Path(thirty.path).read_bytes()
    header = len(b"afar-mock-track\n")
    assert len(Path(sixty.path).read_bytes()) - header == 2 * (
        len(Path(thirty.path).read_bytes()) - header
    )
    assert sixty.metadata["duration_s"] == 60
    assert len(sixty.metadata["composition_plan"]["chunks"]) == 2


def test_elevenlabs_scales_the_timeout_and_sends_the_multi_chunk_plan(
    tmp_path: Path, monkeypatch
):
    from afar.render.elevenlabs import ElevenLabsRenderer

    renderer = ElevenLabsRenderer("test-key", tmp_path / "audio")
    captured: dict[str, object] = {}

    def fake_post(body: bytes, *, timeout=None):
        captured["body"] = body
        captured["timeout"] = timeout
        return b"\x01\x02\x03", {}

    monkeypatch.setattr(renderer, "_post", fake_post)

    renderer.render(_intent().validate(), seed=1)
    assert captured["timeout"] == 90.0  # the floor at the 30s default

    renderer.render(_intent(lyrics=_long_lyrics()).validate(), seed=1, duration_s=120)
    assert captured["timeout"] == 360.0  # max(90, 3 x 120)
    plan = json.loads(captured["body"])["composition_plan"]
    assert len(plan["chunks"]) == 4
    assert sum(c["duration_ms"] for c in plan["chunks"]) == 120_000


def test_player_execute_passes_its_duration_to_the_renderer(tmp_path: Path):
    from ensemble.providers.model import MockProvider

    from afar.agents.personas import PERSONAS
    from afar.agents.player import Player
    from afar.config import _mock_players
    from afar.render.base import MockRenderer

    player = Player(
        PERSONAS["silt"], MockProvider(responder=_mock_players), MockRenderer(tmp_path / "audio")
    )
    decision = player.decide(player.perceive({}))
    player.duration_s = 60
    artifact = player.execute(decision)
    assert artifact.metadata["render"]["duration_s"] == 60
    assert len(artifact.metadata["render"]["composition_plan"]["chunks"]) == 2
