"""DNA -> Persona compiler: structure, determinism, few-shot validity, and a
compile-all smoke over the COMMITTED roster files (the reviewed artifacts).

Committed roster files may carry human review edits on top of compiler
output, so the smoke validates contracts (five sections, ears line, a legal
few-shot Intent, identity metadata) — never byte-equality with a recompile.
"""

import json
from pathlib import Path

import pytest

from afar.agents.persona_compiler import (
    HOUSE_ADDRESSES,
    compile_persona,
    compile_roster_entry,
    extract_example_intent,
    normalize_dna,
)
from afar.agents.roster import ROSTER_DIR, load_roster, load_roster_entries
from afar.intent import ERAS, SONIC_AXES, Intent, register_player_ids, registered_player_ids

TUNZ = Path(__file__).parent / "fixtures" / "tunz"
ARTISTS = sorted(d.name for d in TUNZ.iterdir())

SECTIONS = (
    "YOUR COMMITMENT",
    "WHAT YOU REFUSE.",
    "HOW YOU LISTEN.",
    "EXAMPLE (",
    "WHAT YOU HEAR.",
    "HOW YOU ANSWER.",
)


def _load(artist: str) -> tuple[dict, dict]:
    dna = json.loads((TUNZ / artist / "dna.json").read_text(encoding="utf-8"))
    profile = json.loads((TUNZ / artist / "profile.json").read_text(encoding="utf-8"))
    return dna, profile


def _compile(artist: str):
    dna, profile = _load(artist)
    return compile_persona(
        dna,
        profile,
        player_id=artist,
        display_name=profile["name"],
        first_name=profile["name"].split()[0],
    )


# --- normalization -------------------------------------------------------------


def test_normalize_dna_translates_the_tunz_dialect():
    dna, _ = _load("hohlraum")
    ndna = normalize_dna(dna)
    # snake_case axes -> schema camelCase, string era -> ordinal
    assert set(ndna["sonicPalette"]) == set(SONIC_AXES)
    assert ndna["era"] == ERAS.index("2020s")
    assert abs(sum(i["weight"] for i in ndna["influences"]) - 1) < 1e-6
    assert len(ndna["influences"]) == 4


def test_normalize_dna_rejects_unknown_era():
    dna, _ = _load("hohlraum")
    with pytest.raises(ValueError):
        normalize_dna({**dna, "era": "3020s"})


# --- compilation ---------------------------------------------------------------


@pytest.mark.parametrize("artist", ARTISTS)
def test_compiled_persona_has_all_five_sections_and_the_ears_contract(artist):
    persona = _compile(artist)
    for marker in SECTIONS:
        assert marker in persona.base_prompt, (artist, marker)
    # the shared ears contract line (PR-30) rides every compiled prompt
    assert "Trust your ears" in persona.base_prompt
    # the house first names are how the room speaks
    for name in HOUSE_ADDRESSES.values():
        assert name in persona.base_prompt


@pytest.mark.parametrize("artist", ARTISTS)
def test_compiled_few_shot_is_a_valid_intent(artist):
    register_player_ids(artist)
    persona = _compile(artist)
    intent = extract_example_intent(persona)
    assert isinstance(intent, Intent)
    assert intent.player_id == artist
    assert len(intent.lyrics.splitlines()) >= 3


def test_compilation_is_deterministic():
    a, b = _compile("josie-ryland"), _compile("josie-ryland")
    assert a.base_prompt == b.base_prompt
    assert a.metadata == b.metadata


def test_persona_metadata_carries_identity_and_addresses():
    persona = _compile("josie-ryland")
    meta = persona.metadata
    assert meta["player_id"] == "josie-ryland"
    assert meta["display_name"] == "Josie Ryland"
    assert meta["first_name"] == "Josie"
    assert meta["addresses"] == HOUSE_ADDRESSES
    assert meta["compiled"] is True


def test_commitment_is_aesthetic_never_influence_relational():
    """Architecture rule 4: no compiled sentence defines the act by its
    relationship to influence (no mimic, no refuser-of-others)."""
    for artist in ARTISTS:
        prompt = _compile(artist).base_prompt.lower()
        for banned in ("mimic", "copy the other", "imitate the other", "resist influence"):
            assert banned not in prompt, (artist, banned)


def test_roster_entry_shape_for_the_web_mirror():
    dna, profile = _load("hohlraum")
    entry = compile_roster_entry(
        dna,
        profile,
        player_id="hohlraum",
        display_name=profile["name"],
        first_name="HOHLRAUM",
        origin="tunz",
        building="res-01",
    )
    for key in ("stance", "role_word", "descriptor", "genre_line", "palette", "base_prompt"):
        assert entry[key], key
    assert isinstance(entry["base_prompt"], list)
    assert entry["building"] == "res-01"


# --- registration guard --------------------------------------------------------


def test_unregistered_player_id_still_fails_validation():
    dna, profile = _load("hohlraum")
    persona = compile_persona(
        dna, profile, player_id="never-registered-act", display_name="X Y", first_name="X"
    )
    with pytest.raises(ValueError, match="player_id"):
        extract_example_intent(persona)


def test_house_trio_is_always_registered():
    assert {"silt", "rust", "keep"} <= set(registered_player_ids())


# --- compile-all smoke over the committed roster -------------------------------


def test_committed_roster_loads_and_every_few_shot_validates():
    entries = load_roster_entries()
    assert len(entries) >= 20, "the full tunz roster plus Vess should be committed"
    personas = load_roster()  # registers the ids
    assert set(personas) == {e["player_id"] for e in entries}
    for pid, persona in personas.items():
        for marker in SECTIONS:
            assert marker in persona.base_prompt, (pid, marker)
        assert "Trust your ears" in persona.base_prompt
        intent = extract_example_intent(persona)
        assert intent.player_id == pid
        assert persona.metadata["display_name"]
        assert persona.metadata["addresses"] == HOUSE_ADDRESSES


def test_committed_roster_carries_vess_in_res_03():
    entries = {e["player_id"]: e for e in load_roster_entries()}
    vess = entries["vess"]
    assert vess["display_name"] == "Vess Camber"
    assert vess["building"] == "res-03"
    assert vess["origin"] == "design"
    # the design's occupied residences: one act per building, no doubles
    buildings = [e["building"] for e in entries.values() if e.get("building")]
    assert len(buildings) == len(set(buildings)) == 4


def test_roster_files_match_loader_expectations():
    for path in sorted(ROSTER_DIR.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        assert path.stem == entry["player_id"]
