"""Mapping oracles, ported one-for-one from afar_music's mapping.test.ts.

These are the parity bar with the TS implementation: if a test here needs to
change, mapping.ts changed and the port must follow (or vice versa) — never
drift them independently.
"""

import pytest

from afar.intent import ERAS, Influence, Intent, SonicPalette, VocalCharacter
from afar.mapping import (
    AXIS_TOKENS,
    LYRIC_LINE_MAX_CHARS,
    LYRIC_MAX_LINES,
    NEGATIVE_STYLE_BUDGET,
    POSITIVE_STYLE_BUDGET,
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
        lyrics="rain keeps its own time",
        rationale="test",
        player_id="silt",
    )
    base.update(overrides)
    return Intent(**base)


def chunk(intent: Intent, lyrics: str = "x") -> dict:
    return build_composition_plan(intent, lyrics).plan["chunks"][0]


# --- mapBipolarAxis ----------------------------------------------------------

def test_right_pole_emits_right_tokens_positive_left_tokens_negative():
    mapped = map_bipolar_axis(1, AXIS_TOKENS["pristineLofi"])
    assert "lo-fi" in mapped["positive"]
    assert "pristine production" in mapped["negative"]


def test_at_the_left_pole_the_arrays_swap():
    mapped = map_bipolar_axis(-1, AXIS_TOKENS["pristineLofi"])
    assert "pristine production" in mapped["positive"]
    assert "lo-fi" in mapped["negative"]


def test_magnitude_controls_positive_token_count():
    hard = map_bipolar_axis(1, AXIS_TOKENS["organicSynthetic"])
    soft = map_bipolar_axis(0.3, AXIS_TOKENS["organicSynthetic"])
    assert len(hard["positive"]) > len(soft["positive"])
    assert len(soft["positive"]) > 0


def test_a_mild_lean_states_a_preference_without_banning_the_opposite_pole():
    # Regression: improvisedStructured -0.2 used to hard-ban "structured
    # songwriting" — every slightly-off-center slider produced a negation as
    # strong as its positive.
    mapped = map_bipolar_axis(0.3, AXIS_TOKENS["coldWarm"])
    assert mapped["negative"] == []


def test_a_strong_lean_bans_only_the_opposing_poles_strongest_token():
    mapped = map_bipolar_axis(0.8, AXIS_TOKENS["coldWarm"])
    assert mapped["negative"] == ["cold tone"]


def test_neutral_values_inside_the_deadzone_contribute_nothing():
    assert map_bipolar_axis(0, AXIS_TOKENS["coldWarm"]) == {"positive": [], "negative": []}
    assert map_bipolar_axis(0.1, AXIS_TOKENS["coldWarm"]) == {"positive": [], "negative": []}


# --- influenceTokens ---------------------------------------------------------

def test_higher_weight_contributes_more_tokens():
    assert len(influence_tokens("jazz", 1)) == 4
    assert len(influence_tokens("jazz", 0.5)) == 2
    assert len(influence_tokens("jazz", 0.25)) == 1


def test_any_nonzero_weight_contributes_at_least_one_token():
    # Regression: Math.round quantized weights under 0.125 to zero tokens —
    # a genre shown as "10%" in the UI contributed nothing.
    assert len(influence_tokens("jazz", 0.1)) == 1
    assert len(influence_tokens("jazz", 0.01)) == 1


def test_zero_weight_contributes_nothing():
    assert influence_tokens("jazz", 0) == []


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


def test_preserves_line_breaks_the_api_limit_is_per_line_not_per_text():
    lyrics = "rain on the glass\nwires hum in the dark\nnobody calls back"
    assert clamp_lyrics(lyrics) == lyrics


def test_clamps_each_line_independently_at_a_word_boundary():
    long_line = " ".join(["rain"] * 60)  # 299 chars
    clamped = clamp_lyrics(f"{long_line}\nshort line")
    first, second = clamped.split("\n")
    assert len(first) <= LYRIC_LINE_MAX_CHARS
    assert first.endswith("rain")  # no mid-word cut
    assert second == "short line"


def test_drops_empty_lines_and_surrounding_whitespace():
    assert clamp_lyrics("  first line  \n\n\n  second line \n") == "first line\nsecond line"


def test_caps_the_number_of_lines():
    lyrics = "\n".join(["la la la"] * 20)
    assert len(clamp_lyrics(lyrics).split("\n")) == LYRIC_MAX_LINES


def test_hard_cuts_a_single_unbroken_word_rather_than_exceeding_the_limit():
    assert len(clamp_lyrics("a" * 300)) == LYRIC_LINE_MAX_CHARS


# --- buildCompositionPlan ----------------------------------------------------

def test_emits_exactly_one_30s_chunk_carrying_lyrics_styles_and_context_adherence():
    built = build_composition_plan(dna_with(), "rain keeps its own time")
    assert len(built.plan["chunks"]) == 1
    c = built.plan["chunks"][0]
    assert c["text"] == "rain keeps its own time"
    assert c["duration_ms"] == TRACK_DURATION_MS
    assert len(c["positive_styles"]) > 0
    assert c["context_adherence"] == "medium"


def test_sends_no_music_v1_keys_styles_live_on_the_chunk_not_global_arrays():
    # Regression: positive_global_styles / negative_global_styles are the
    # music_v1 MusicPrompt schema. music_v2's CompositionPlan is chunks-only,
    # so everything in those keys was silently ignored by the API.
    built = build_composition_plan(dna_with(), "x")
    assert "positive_global_styles" not in built.plan
    assert "negative_global_styles" not in built.plan
    assert set(built.plan) == {"chunks"}


def test_respects_the_documented_style_budget_even_at_every_extreme():
    c = chunk(
        dna_with(
            sonicPalette=_palette(
                pristineLofi=1,
                sparseDense=1,
                coldWarm=-1,
                improvisedStructured=1,
                loudQuiet=-1,
                organicSynthetic=1,
                darkHopeful=-1,
            ),
            vocalCharacter=VocalCharacter(whispersScreams=1, cleanDamaged=1),
        )
    )
    assert len(c["positive_styles"]) <= POSITIVE_STYLE_BUDGET
    assert len(c["negative_styles"]) <= NEGATIVE_STYLE_BUDGET


def test_era_drives_bpm_and_the_lead_production_token():
    c = chunk(dna_with(era=ERAS.index("1980s")))
    assert "118 BPM" in c["positive_styles"]
    assert "1980s production" in c["positive_styles"]


def test_loud_quiet_slider_modulates_the_era_bpm():
    # Quiet artists slow down (up to 20%); loud artists speed up (up to 10%).
    quiet = chunk(dna_with(era=ERAS.index("1970s"), sonicPalette=_palette(loudQuiet=0.8)))
    assert "88 BPM" in quiet["positive_styles"]  # 105 x 0.84
    loud = chunk(dna_with(era=ERAS.index("1970s"), sonicPalette=_palette(loudQuiet=-1)))
    assert "116 BPM" in loud["positive_styles"]  # 105 x 1.1, rounded


def test_the_lead_influence_always_anchors_the_genre_with_two_tokens():
    c = chunk(
        dna_with(
            influences=(
                Influence("folk", 0.28),
                Influence("americana", 0.24),
                Influence("chamber pop", 0.24),
                Influence("ambient", 0.24),
            )
        )
    )
    assert "folk" in c["positive_styles"]
    assert "folk instrumentation" in c["positive_styles"]


def test_a_pushed_slider_lands_in_both_chunk_style_arrays_and_in_provenance():
    built = build_composition_plan(
        dna_with(sonicPalette=_palette(organicSynthetic=1)), "x"
    )
    assert "synthetic textures" in built.plan["chunks"][0]["positive_styles"]
    assert "organic instrumentation" in built.plan["chunks"][0]["negative_styles"]
    assert "sonicPalette.organicSynthetic" in built.provenance


def test_a_mildly_leaning_slider_produces_no_negative_ban():
    c = chunk(dna_with(sonicPalette=_palette(improvisedStructured=-0.2)))
    assert c["negative_styles"] == []


def test_neutral_axes_stay_out_of_provenance():
    built = build_composition_plan(dna_with(), "x")
    assert not any(p.startswith("sonicPalette.") for p in built.provenance)


def test_active_vocal_pad_axes_always_claim_a_style_slot():
    # The pad is a headline control: it must not be crowded out of the budget
    # by influence and axis tokens.
    c = chunk(dna_with(vocalCharacter=VocalCharacter(whispersScreams=0.3, cleanDamaged=0.3)))
    joined = " ".join(c["positive_styles"])
    assert "belted" in joined or "powerful" in joined
    assert "rasp" in joined


def test_moderate_vocal_pad_positions_emit_moderate_tokens_not_the_extremes():
    # Regression: whispersScreams 0.6 fell in the two-token band and emitted
    # "screamed vocals" as a positive style for a soul belter.
    c = chunk(dna_with(vocalCharacter=VocalCharacter(whispersScreams=0.6, cleanDamaged=0.3)))
    assert "powerful belted vocals" in c["positive_styles"]
    assert "screamed vocals" not in c["positive_styles"]
    assert "damaged vocal texture" not in c["positive_styles"]


def test_extreme_vocal_pad_positions_still_reach_the_extremes():
    c = chunk(dna_with(vocalCharacter=VocalCharacter(whispersScreams=0.9, cleanDamaged=0.9)))
    assert "screamed vocals" in c["positive_styles"]
    assert "damaged vocal texture" in c["positive_styles"]


def test_a_strong_whisper_lean_bans_screaming_and_vice_versa():
    c = chunk(dna_with(vocalCharacter=VocalCharacter(whispersScreams=-0.9, cleanDamaged=0)))
    assert "whispered vocals" in c["positive_styles"]
    assert "screamed vocals" in c["negative_styles"]


def test_sparse_quiet_organic_together_read_as_a_solo_performance():
    c = chunk(
        dna_with(sonicPalette=_palette(sparseDense=-0.7, loudQuiet=0.8, organicSynthetic=-0.9))
    )
    assert "intimate solo performance" in c["positive_styles"]
    assert "full band arrangement" in c["negative_styles"]
    assert len(c["negative_styles"]) <= NEGATIVE_STYLE_BUDGET


def test_the_solo_performance_combo_needs_all_three_axes_aligned():
    c = chunk(
        dna_with(sonicPalette=_palette(sparseDense=-0.7, loudQuiet=-0.5, organicSynthetic=-0.9))
    )
    assert "intimate solo performance" not in c["positive_styles"]
    assert "full band arrangement" not in c["negative_styles"]


def test_era_and_organic_tokens_never_force_genre_or_instrumentation():
    # Regression: "1950s rock and roll production" and "live drums" were
    # dragging quiet folk artists toward full-band rock.
    c = chunk(
        dna_with(era=ERAS.index("1950s"), sonicPalette=_palette(organicSynthetic=-1))
    )
    joined = " | ".join(c["positive_styles"])
    assert "rock and roll" not in joined
    assert "live drums" not in joined
    assert "trap hi-hats" not in joined
    assert "organic instrumentation" in c["positive_styles"]


def test_context_adherence_rides_inside_the_chunk_where_music_v2_reads_it():
    # Regression: context_adherence was sent as a top-level request key, which
    # the API ignores — every chunk silently ran at the documented default
    # ("high") regardless of the improvised<->structured slider.
    built = build_composition_plan(
        dna_with(sonicPalette=_palette(improvisedStructured=-1)), "x"
    )
    assert built.plan["chunks"][0]["context_adherence"] == "low"
    assert built.context_adherence == "low"


def test_duplicate_tokens_are_deduped_preserving_first_seen_order():
    # Two influences sharing a genre would emit "jazz" twice; selection keeps one.
    c = chunk(
        dna_with(
            influences=(
                Influence("jazz", 0.5),
                Influence("jazz", 0.3),
                Influence("ambient", 0.1),
                Influence("drone", 0.1),
            )
        )
    )
    positives = c["positive_styles"]
    assert positives.count("jazz") == 1
    assert positives.count("jazz instrumentation") == 1
    assert len(positives) == len(set(positives))
