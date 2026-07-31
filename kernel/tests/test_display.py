"""Pins afar.display.normalize_act_names to the same behavior as the vitest
cases over web/lib/normalize-act-names.mjs (the two are one-to-one mirrors)."""

from afar.display import normalize_act_names


def test_maps_capitalized_act_ids_to_first_names():
    assert (
        normalize_act_names("Rust, ground cracks so silt has somewhere to go")
        == "Roan, ground cracks so silt has somewhere to go"
    )
    assert (
        normalize_act_names("Silt built a floor and called it warm")
        == "Delta built a floor and called it warm"
    )


def test_vocative_keep():
    assert (
        normalize_act_names("Keep, that chord doesn't stop ringing")
        == "Evers, that chord doesn't stop ringing"
    )


def test_double_vocative():
    assert (
        normalize_act_names("Keep, Silt, listen to what's under your resolve.")
        == "Evers, Delta, listen to what's under your resolve."
    )


def test_possessives_carry_over_preserving_apostrophe_glyph():
    assert (
        normalize_act_names("Rust's dead tape and Keep's held chord")
        == "Roan's dead tape and Evers's held chord"
    )
    assert normalize_act_names("Silt’s floor-settling") == "Delta’s floor-settling"


def test_lowercase_common_noun_uses_untouched():
    assert (
        normalize_act_names("it just goes under enough silt to hold weight")
        == "it just goes under enough silt to hold weight"
    )
    assert normalize_act_names("everything you keep still rots") == "everything you keep still rots"
    assert normalize_act_names("keep the hum; rust never sleeps") == "keep the hum; rust never sleeps"


def test_word_boundaries():
    assert (
        normalize_act_names("Keeper of the Rusty Silted gate") == "Keeper of the Rusty Silted gate"
    )


def test_empty_string():
    assert normalize_act_names("") == ""


def test_idempotent():
    once = normalize_act_names("Rust, I heard the crack — Keep's chord, Silt's loam.")
    assert normalize_act_names(once) == once
