"""Intent schema tests: validate() mirrors every schema.ts refinement, the
content hash is stable, and from_json survives real model formatting."""

import json

import pytest

from afar.intent import ERAS, Influence, Intent, SonicPalette, VocalCharacter, normalize_influences


def make_intent(**overrides) -> Intent:
    base = dict(
        seedPrompt="test artist",
        era=ERAS.index("2020s"),
        influences=(
            Influence("synthpop", 0.4),
            Influence("shoegaze", 0.3),
            Influence("trip-hop", 0.2),
            Influence("ambient", 0.1),
        ),
        sonicPalette=SonicPalette(0, 0, 0, 0, 0, 0, 0),
        vocalCharacter=VocalCharacter(0, 0),
        lyricalObsessions=("rain",),
        visualStyle=("neon fog",),
        line="I begin where the rain does.",
        rationale="A neutral palette to start from; everything else is a reply.",
        player_id="silt",
    )
    base.update(overrides)
    return Intent(**base)


# --- validate ----------------------------------------------------------------

def test_validate_accepts_a_valid_intent():
    assert make_intent().validate() is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"seedPrompt": ""},
        {"era": 11},
        {"era": -1},
        {"era": 1.5},
        {"era": True},  # bools are not eras
        {"influences": (Influence("a", 0.5), Influence("b", 0.5))},  # not 4
        {
            "influences": (
                Influence("a", 0.4),
                Influence("b", 0.3),
                Influence("c", 0.2),
                Influence("d", 0.2),
            )
        },  # sums to 1.1
        {
            "influences": (
                Influence("a", 1.2),
                Influence("b", 0.0),
                Influence("c", 0.0),
                Influence("d", -0.2),
            )
        },  # weights out of 0..1
        {
            "influences": (
                Influence("", 0.4),
                Influence("b", 0.3),
                Influence("c", 0.2),
                Influence("d", 0.1),
            )
        },  # empty genre
        {"sonicPalette": SonicPalette(1.5, 0, 0, 0, 0, 0, 0)},
        {"vocalCharacter": VocalCharacter(0, -2)},
        {"lyricalObsessions": ("Rain", "rain")},  # case-insensitive dup
        {"visualStyle": ("fog", "")},  # empty tag
        {"player_id": "muse"},
        {"line": "   "},
        {"rationale": ""},
    ],
)
def test_validate_rejects(overrides):
    with pytest.raises(ValueError):
        make_intent(**overrides).validate()


def test_weight_sum_tolerance_matches_zod():
    # abs(sum - 1) < 1e-6 passes; exactly 1e-6 off fails.
    ok = make_intent(
        influences=(
            Influence("a", 0.4),
            Influence("b", 0.3),
            Influence("c", 0.2),
            Influence("d", 0.1 + 1e-8),
        )
    )
    ok.validate()


# --- to_dna_dict / content_hash ----------------------------------------------

def test_to_dna_dict_is_the_exact_schema_ts_shape():
    dna = make_intent().to_dna_dict()
    assert set(dna) == {
        "seedPrompt",
        "era",
        "influences",
        "sonicPalette",
        "vocalCharacter",
        "lyricalObsessions",
        "visualStyle",
    }
    # AFAR additions never leak into the DNA shape.
    assert "line" not in dna and "player_id" not in dna
    assert dna["influences"][0] == {"genre": "synthpop", "weight": 0.4}
    assert set(dna["sonicPalette"]) == {
        "pristineLofi",
        "sparseDense",
        "coldWarm",
        "improvisedStructured",
        "loudQuiet",
        "organicSynthetic",
        "darkHopeful",
    }
    json.dumps(dna)  # must be JSON-serializable as-is


def test_content_hash_is_stable_and_sensitive():
    a, b = make_intent(), make_intent()
    assert a.content_hash() == b.content_hash()
    assert len(a.content_hash()) == 64
    # The frame is part of the act: a different line hashes differently.
    assert make_intent(line="Different.").content_hash() != a.content_hash()
    assert make_intent(era=0).content_hash() != a.content_hash()


# --- from_json ---------------------------------------------------------------

def _payload() -> dict:
    intent = make_intent()
    return dict(
        intent.to_dna_dict(),
        line=intent.line,
        rationale=intent.rationale,
        player_id=intent.player_id,
    )


def test_from_json_parses_plain_json():
    intent = Intent.from_json(json.dumps(_payload()))
    assert intent == make_intent()


def test_from_json_tolerates_markdown_fences():
    fenced = "```json\n" + json.dumps(_payload()) + "\n```"
    assert Intent.from_json(fenced) == make_intent()


def test_from_json_tolerates_prose_around_the_object():
    wrapped = "Here is my intent:\n" + json.dumps(_payload()) + "\nThat is all."
    assert Intent.from_json(wrapped) == make_intent()


def test_from_json_rejects_non_json():
    with pytest.raises(ValueError):
        Intent.from_json("I would rather describe it in words.")


def test_from_json_rejects_missing_fields():
    payload = _payload()
    del payload["sonicPalette"]
    with pytest.raises(ValueError):
        Intent.from_json(json.dumps(payload))


def test_from_json_rejects_invalid_values():
    payload = _payload()
    payload["era"] = 42
    with pytest.raises(ValueError):
        Intent.from_json(json.dumps(payload))


# --- normalize_influences ----------------------------------------------------

def test_normalize_influences_rescales_to_sum_1():
    raw = (Influence("a", 2.0), Influence("b", 1.0), Influence("c", 1.0), Influence("d", 0.0))
    normalized = normalize_influences(raw)
    assert abs(sum(i.weight for i in normalized) - 1) < 1e-9
    assert normalized[0].weight == 0.5


def test_normalize_influences_degrades_to_equal_weights_on_zero_total():
    raw = (Influence("a", 0.0), Influence("b", 0.0), Influence("c", 0.0), Influence("d", 0.0))
    normalized = normalize_influences(raw)
    assert [i.weight for i in normalized] == [0.25, 0.25, 0.25, 0.25]
