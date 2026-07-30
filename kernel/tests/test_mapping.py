"""Mapping oracles, ported one-for-one from afar_music's mapping.test.ts.

These are the parity bar with the TS implementation: if a test here needs to
change, mapping.ts changed and the port must follow (or vice versa) — never
drift them independently.
"""

import pytest

from afar.intent import ERAS, Influence, Intent, SonicPalette, VocalCharacter
from afar.mapping import (
    AXIS_TOKENS,
    LYRICS_MAX_CHARS,
    TRACK_DURATION_MS,
    build_composition_plan,
    clamp_lyrics,
    context_adherence_for,
    influence_tokens,
    map_bipolar_axis,
)

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


def _palette(**overrides) -> SonicPalette:
    return SonicPalette(**{**_NEUTRAL, **overrides})


def dna_with(**overrides) -> Intent:
    base = dict(
        seedPrompt="test artist",
        era=ERAS.index("2020s"),
        influences=(
            Influence("synthpop", 0.4),
            Influence("shoegaze", 0.3),
            Influence("trip-hop", 0.2),
            Influence("ambient", 0.1),
        ),
        sonicPalette=_palette(),
        vocalCharacter=VocalCharacter(0, 0),
        lyricalObsessions=("rain",),
        visualStyle=("neon fog",),
        line="x",
        rationale="test",
        player_id="silt",
    )
    base.update(overrides)
    return Intent(**base)


# --- mapBipolarAxis ----------------------------------------------------------

def test_right_pole_emits_right_tokens_positive_left_tokens_negative():
    mapped = map_bipolar_axis(1, AXIS_TOKENS["pristineLofi"])
    assert "lo-fi" in mapped["positive"]
    assert "pristine production" in mapped["negative"]


def test_at_the_left_pole_the_arrays_swap():
    mapped = map_bipolar_axis(-1, AXIS_TOKENS["pristineLofi"])
    assert "pristine production" in mapped["positive"]
    assert "lo-fi" in mapped["negative"]


def test_magnitude_controls_token_count():
    hard = map_bipolar_axis(1, AXIS_TOKENS["organicSynthetic"])
    soft = map_bipolar_axis(0.3, AXIS_TOKENS["organicSynthetic"])
    assert len(hard["positive"]) > len(soft["positive"])
    assert len(soft["positive"]) > 0


def test_neutral_values_inside_the_deadzone_contribute_nothing():
    assert map_bipolar_axis(0, AXIS_TOKENS["coldWarm"]) == {"positive": [], "negative": []}
    assert map_bipolar_axis(0.1, AXIS_TOKENS["coldWarm"]) == {"positive": [], "negative": []}


# --- influenceTokens ---------------------------------------------------------

def test_higher_weight_contributes_more_tokens():
    assert len(influence_tokens("jazz", 1)) == 4
    assert len(influence_tokens("jazz", 0.5)) == 2
    assert len(influence_tokens("jazz", 0.25)) == 1


def test_negligible_weight_contributes_nothing():
    assert influence_tokens("jazz", 0.1) == []


# --- contextAdherenceFor -----------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-1, "low"),
        (-0.4, "low"),
        (-0.2, "medium"),
        (0, "medium"),
        (0.33, "medium"),
        (0.4, "high"),
        (1, "high"),
    ],
)
def test_context_adherence_thirds(value, expected):
    assert context_adherence_for(value) == expected


# --- clampLyrics -------------------------------------------------------------

def test_leaves_short_lyrics_untouched():
    assert clamp_lyrics("rain on the elevator glass") == "rain on the elevator glass"


def test_clamps_long_lyrics_to_the_limit_at_a_word_boundary():
    long = " ".join(["rain"] * 60)  # 299 chars
    clamped = clamp_lyrics(long)
    assert len(clamped) <= LYRICS_MAX_CHARS
    assert clamped.endswith("rain")  # no mid-word cut


def test_hard_cuts_a_single_unbroken_word():
    assert len(clamp_lyrics("a" * 300)) == LYRICS_MAX_CHARS


# --- buildCompositionPlan ----------------------------------------------------

def test_always_emits_exactly_one_30s_chunk_whose_text_is_the_lyrics():
    built = build_composition_plan(dna_with(), "rain keeps its own time")
    assert len(built.plan["chunks"]) == 1
    assert built.plan["chunks"][0] == {
        "text": "rain keeps its own time",
        "duration_ms": TRACK_DURATION_MS,
        "positive_styles": [],
        "negative_styles": [],
    }


def test_era_drives_bpm_and_production_tokens():
    built = build_composition_plan(dna_with(era=ERAS.index("1980s")), "x")
    assert "118 BPM" in built.plan["positive_global_styles"]
    assert "big analog reverb" in built.plan["positive_global_styles"]


def test_loud_quiet_slider_modulates_the_era_bpm():
    # Quiet artists slow down (up to 20%); loud artists speed up (up to 10%).
    quiet = build_composition_plan(
        dna_with(era=ERAS.index("1970s"), sonicPalette=_palette(loudQuiet=0.8)), "x"
    )
    assert "88 BPM" in quiet.plan["positive_global_styles"]  # 105 x 0.84
    loud = build_composition_plan(
        dna_with(era=ERAS.index("1970s"), sonicPalette=_palette(loudQuiet=-1)), "x"
    )
    assert "116 BPM" in loud.plan["positive_global_styles"]  # 105 x 1.1, rounded


def test_era_and_organic_tokens_never_force_genre_or_instrumentation():
    # Regression: "1950s rock and roll production" and "live drums" were
    # dragging quiet folk artists toward full-band rock.
    built = build_composition_plan(
        dna_with(era=ERAS.index("1950s"), sonicPalette=_palette(organicSynthetic=-1)), "x"
    )
    joined = " | ".join(built.plan["positive_global_styles"])
    assert "rock and roll" not in joined
    assert "live drums" not in joined
    assert "trap hi-hats" not in joined
    assert "organic instrumentation" in built.plan["positive_global_styles"]


def test_a_pushed_slider_lands_in_both_style_arrays_and_in_provenance():
    built = build_composition_plan(dna_with(sonicPalette=_palette(organicSynthetic=1)), "x")
    assert "synthetic textures" in built.plan["positive_global_styles"]
    assert "organic instrumentation" in built.plan["negative_global_styles"]
    assert "sonicPalette.organicSynthetic" in built.provenance


def test_neutral_axes_stay_out_of_provenance():
    built = build_composition_plan(dna_with(), "x")
    assert not any(p.startswith("sonicPalette.") for p in built.provenance)


def test_moderate_vocal_pad_positions_emit_moderate_tokens_not_extremes():
    # Regression: any value past the deadzone used to emit "screamed vocals" /
    # "damaged vocal texture" at full strength.
    built = build_composition_plan(
        dna_with(vocalCharacter=VocalCharacter(whispersScreams=0.3, cleanDamaged=0.3)), "x"
    )
    positives = built.plan["positive_global_styles"]
    assert "screamed vocals" not in positives
    assert "damaged vocal texture" not in positives
    joined = " ".join(positives)
    assert "belted" in joined or "powerful" in joined
    assert "rasp" in joined


def test_extreme_vocal_pad_positions_still_reach_the_extremes():
    built = build_composition_plan(
        dna_with(vocalCharacter=VocalCharacter(whispersScreams=0.9, cleanDamaged=0.9)), "x"
    )
    assert "screamed vocals" in built.plan["positive_global_styles"]
    assert "damaged vocal texture" in built.plan["positive_global_styles"]


def test_sparse_quiet_organic_together_read_as_a_solo_performance():
    built = build_composition_plan(
        dna_with(sonicPalette=_palette(sparseDense=-0.7, loudQuiet=0.8, organicSynthetic=-0.9)),
        "x",
    )
    assert "intimate solo performance" in built.plan["positive_global_styles"]
    assert "full band arrangement" in built.plan["negative_global_styles"]
    assert "percussion" in built.plan["negative_global_styles"]


def test_the_solo_performance_combo_needs_all_three_axes_aligned():
    built = build_composition_plan(
        dna_with(sonicPalette=_palette(sparseDense=-0.7, loudQuiet=-0.5, organicSynthetic=-0.9)),
        "x",
    )
    assert "intimate solo performance" not in built.plan["positive_global_styles"]
    assert "full band arrangement" not in built.plan["negative_global_styles"]


def test_the_lead_influence_always_anchors_the_genre_with_two_tokens():
    # A folk artist whose weights are spread thin still needs 'folk' to
    # outweigh palette adjectives.
    built = build_composition_plan(
        dna_with(
            influences=(
                Influence("folk", 0.28),
                Influence("americana", 0.24),
                Influence("chamber pop", 0.24),
                Influence("ambient", 0.24),
            )
        ),
        "x",
    )
    assert "folk" in built.plan["positive_global_styles"]
    assert "folk instrumentation" in built.plan["positive_global_styles"]


def test_vocal_pad_emits_vocal_tokens():
    built = build_composition_plan(
        dna_with(vocalCharacter=VocalCharacter(whispersScreams=-0.9, cleanDamaged=0)), "x"
    )
    assert "whispered vocals" in built.plan["positive_global_styles"]
    assert "screamed vocals" in built.plan["negative_global_styles"]


def test_exposes_context_adherence_from_the_improvised_structured_axis():
    built = build_composition_plan(
        dna_with(sonicPalette=_palette(improvisedStructured=-1)), "x"
    )
    assert built.context_adherence == "low"


def test_duplicate_tokens_are_deduped_preserving_first_seen_order():
    # Two influences sharing a genre would emit "jazz" twice; the plan keeps one.
    built = build_composition_plan(
        dna_with(
            influences=(
                Influence("jazz", 0.5),
                Influence("jazz", 0.3),
                Influence("ambient", 0.1),
                Influence("drone", 0.1),
            )
        ),
        "x",
    )
    positives = built.plan["positive_global_styles"]
    assert positives.count("jazz") == 1
    assert positives.count("jazz instrumentation") == 1
    assert len(positives) == len(set(positives))
