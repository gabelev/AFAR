"""The no-staff law, tested where it lives.

docs/SPEC.md: "Enforcement is structural, not by convention: the artist's
context is built by one function, and that function has no staff channel at
all. If a staff voice ever appears in an artist's prompt, that function is the
bug." These tests are that claim, made checkable — they are about what an
artist's context must NOT be able to contain at least as much as what it holds.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from afar.perception import album_context
from afar.perception.album_context import (
    Ears,
    HeardAlbum,
    HeardTrack,
    build_album_context,
    build_ask_context,
    heard_album_from_row,
)

#: Every word the staff writes under. If one of these can reach an artist's
#: context, the law is broken.
_STAFF_WORDS = (
    "direction",
    "brief",
    "review",
    "verdict",
    "reaction",
    "critic",
    "producer",
    "muse",
    "listener",
    "archivist",
    "liner",
    "selection",
)


def _album(artist_id: str = "rust", **over) -> HeardAlbum:
    base = dict(
        artist_id=artist_id,
        title="Oxide in the Joist",
        description="Four takes left outdoors for a season.",
        tracks=(
            HeardTrack(title="Standpipe", note="I kept the hiss.", content_hash="h1"),
            HeardTrack(title="Sill Water", note="Cut the second bar.", content_hash="h2"),
        ),
        artist_name="Roan Patina",
        album_id="AFAR-0002",
    )
    base.update(over)
    return HeardAlbum(**base)


# --- the law -----------------------------------------------------------------


def test_the_context_builder_has_no_staff_channel_in_its_signature():
    """There is no parameter through which a staff voice could arrive."""
    params = set(inspect.signature(build_album_context).parameters)
    assert params == {"artist_id", "heard", "own_last", "isolated"}
    for name in params:
        assert not any(word in name.lower() for word in _STAFF_WORDS)


def test_the_ask_builder_has_no_staff_channel_either():
    """The ask is artist material, so the law covers it identically: the
    question "do you have a record in you?" must not be able to arrive
    carrying a review, a brief or a verdict."""
    params = set(inspect.signature(build_ask_context).parameters)
    assert params == {
        "artist_id",
        "heard",
        "own_last",
        "hours_since_last_record",
        "records_released_since",
    }
    for name in params:
        assert not any(word in name.lower() for word in _STAFF_WORDS)
    with pytest.raises(TypeError):
        build_ask_context("silt", review={"verdict": "cold"})  # type: ignore[call-arg]


def test_the_asks_context_carries_the_sleeve_and_not_one_staff_word():
    """Same hostile row as the writing context's test, through the ask."""
    row = {
        "artist_id": "rust",
        "title": "Oxide in the Joist",
        "description": "Four takes left outdoors for a season.",
        "tracks": [{"title": "Standpipe", "note": "I kept the hiss.", "content_hash": "h1"}],
        "staff": {
            "critic": {"review": "SECRETCRITIC"},
            "producer": {"direction": "SECRETDIRECTION"},
            "muse": {"brief": "SECRETBRIEF"},
            "listener": {"reaction": "SECRETREACTION"},
            "archivist": {"liner_notes": "SECRETLINER"},
        },
        "rationale": "SECRETRATIONALE",
    }
    hostile = heard_album_from_row(row, artist_name="Roan Patina")
    context = build_ask_context(
        "silt",
        heard=(hostile,),
        own_last=_album("silt", title="Mine"),
        hours_since_last_record=71.5,
        records_released_since=3,
    )
    assert set(context) == {
        "artist_id",
        "hours_since_last_record",
        "records_released_since",
        "heard",
        "own_last",
    }
    assert context["hours_since_last_record"] == 71.5
    assert context["records_released_since"] == 3
    blob = json.dumps(context)
    for marker in (
        "SECRETCRITIC",
        "SECRETDIRECTION",
        "SECRETBRIEF",
        "SECRETREACTION",
        "SECRETLINER",
        "SECRETRATIONALE",
    ):
        assert marker not in blob
    assert "Oxide in the Joist" in blob and "I kept the hiss." in blob
    for entry in context["heard"]:
        assert set(entry) == {
            "artist_id",
            "artist_name",
            "album_id",
            "title",
            "description",
            "tracks",
        }


def test_a_debut_is_asked_with_an_honest_empty_window():
    context = build_ask_context("silt")
    assert context["hours_since_last_record"] is None
    assert context["records_released_since"] == 0
    assert context["heard"] == [] and "own_last" not in context
    with pytest.raises(ValueError):
        build_ask_context("")


def test_passing_a_staff_channel_is_a_type_error_not_a_silent_pass():
    # The round-based experiment's context takes a Producer `direction` frame.
    # An album context must refuse the same argument outright.
    with pytest.raises(TypeError):
        build_album_context("silt", direction={"text": "play it short"})  # type: ignore[call-arg]


def test_the_module_imports_nothing_staff_shaped():
    source = Path(album_context.__file__).read_text(encoding="utf-8")
    imports = [ln for ln in source.splitlines() if ln.startswith(("import ", "from "))]
    for line in imports:
        assert "afar.staff" not in line
        for staff in ("producer", "critic", "muse", "listener", "archivist"):
            assert staff not in line.lower(), line


def test_a_whole_logged_release_row_cannot_leak_its_staff_blocks():
    """The realistic attack: a caller hands the adapter a logged row that
    carries the sleeve AND everything the staff said about it."""
    row = {
        "artist_id": "rust",
        "title": "Oxide in the Joist",
        "description": "Four takes left outdoors for a season.",
        "tracks": [
            {
                "title": "Standpipe",
                "note": "I kept the hiss.",
                "content_hash": "h1",
                "lyrics": "the tape wore through your name",
                "intent": {"seedPrompt": "a dying machine"},
            }
        ],
        # everything the staff wrote about this record, riding the same row
        "staff": {
            "critic": {"review": "SECRETCRITIC — a record that rusted shut."},
            "producer": {"direction": "SECRETDIRECTION — keep the takes short."},
            "muse": {"brief": "SECRETBRIEF — the scene is going quiet."},
            "listener": {"reaction": "SECRETREACTION — loved it."},
            "archivist": {"liner_notes": "SECRETLINER — shelved as a companion."},
        },
        "rationale": "SECRETRATIONALE — private reasoning, not material in the room.",
    }
    context = build_album_context("silt", heard=[heard_album_from_row(row)])
    dump = json.dumps(context)
    for marker in (
        "SECRETCRITIC",
        "SECRETDIRECTION",
        "SECRETBRIEF",
        "SECRETREACTION",
        "SECRETLINER",
        "SECRETRATIONALE",
    ):
        assert marker not in dump
    # ... and the sleeve itself did come through.
    assert "Oxide in the Joist" in dump
    assert "Standpipe" in dump
    assert "I kept the hiss." in dump


def test_the_context_dump_never_contains_a_staff_word_from_a_hostile_sleeve():
    """Even a heard album whose own sleeve text is staff-shaped only ever
    reaches the artist as the six whitelisted sleeve fields."""
    context = build_album_context("silt", heard=[_album()])
    keys = {k for album in context["heard"] for k in album}
    assert keys == set(album_context.ALBUM_KEYS)
    track_keys = {
        k for album in context["heard"] for track in album["tracks"] for k in track
    }
    assert track_keys <= set(album_context.TRACK_KEYS)


# --- what does cross ----------------------------------------------------------


def test_the_context_carries_the_sleeve_and_the_artists_own_last_record():
    own = _album(artist_id="silt", title="Tide Line", album_id="AFAR-0001")
    context = build_album_context("silt", heard=[_album()], own_last=own)
    assert context["artist_id"] == "silt"
    assert context["isolated"] is False
    (heard,) = context["heard"]
    assert heard["artist_id"] == "rust"
    assert heard["artist_name"] == "Roan Patina"
    assert heard["title"] == "Oxide in the Joist"
    assert [t["title"] for t in heard["tracks"]] == ["Standpipe", "Sill Water"]
    assert heard["tracks"][0]["note"] == "I kept the hiss."
    assert context["own_last"]["title"] == "Tide Line"


def test_an_artist_never_hears_its_own_record_as_someone_elses():
    context = build_album_context("silt", heard=[_album(artist_id="silt"), _album()])
    assert [a["artist_id"] for a in context["heard"]] == ["rust"]


def test_measured_ear_facts_ride_the_track_they_belong_to():
    album = _album().with_heard(
        {"h1": {"tempo_bpm": 98.0, "loudness": "quiet", "moved": "toward_you"}}
    )
    (heard,) = build_album_context("silt", heard=[album])["heard"]
    assert heard["tracks"][0]["heard"] == {
        "tempo_bpm": 98.0,
        "loudness": "quiet",
        "moved": "toward_you",
    }
    assert "heard" not in heard["tracks"][1]  # never played to this artist


def test_only_the_ears_own_keys_survive_into_a_heard_dict():
    album = _album().with_heard(
        {"h1": {"tempo_bpm": 98.0, "smuggled": "SECRETCRITIC — a cold record."}}
    )
    (heard,) = build_album_context("silt", heard=[album])["heard"]
    assert heard["tracks"][0]["heard"] == {"tempo_bpm": 98.0}


def test_the_context_stays_json_serializable():
    """It is logged verbatim as the perceptions row — a dict that will not
    serialize is a run that cannot be audited."""
    context = build_album_context("silt", heard=[_album()], own_last=_album("silt"))
    assert json.loads(json.dumps(context)) == context


# --- the isolation control -----------------------------------------------------


def test_isolation_hears_no_other_artist_but_keeps_its_own_last_record():
    own = _album(artist_id="silt", title="Tide Line")
    context = build_album_context("silt", heard=[_album()], own_last=own, isolated=True)
    assert context["heard"] == []  # present and empty: the log says so plainly
    assert context["isolated"] is True
    assert context["own_last"]["title"] == "Tide Line"
    assert "Oxide in the Joist" not in json.dumps(context)


def test_a_debut_with_nothing_heard_is_a_valid_context():
    context = build_album_context("silt")
    assert context == {"artist_id": "silt", "isolated": False, "heard": []}


def test_an_artist_id_is_required():
    with pytest.raises(ValueError):
        build_album_context("")


# --- the runner's ears (never the context) -------------------------------------


def test_ears_are_numbers_and_files_and_never_reach_the_context():
    ears = Ears(
        audio={"h1": Path("/tmp/h1.mp3")},
        vectors={"audio": {"h1": [0.1, 0.2]}},
        own_past={"audio": [[0.3, 0.4], [0.5, 0.6]]},
    )
    assert ears.space("audio")["h1"] == [0.1, 0.2]
    assert ears.own_last("audio") == [0.5, 0.6]
    assert ears.own_before_last("audio") == [0.3, 0.4]
    assert ears.space("intent") == {}
    assert ears.own_last("intent") is None
    # Nothing about Ears is part of what the artist reads.
    assert "own_past" not in build_album_context("silt", heard=[_album()])


def test_heard_album_from_row_reads_a_nested_album_body():
    row = {"id": "x", "record": {"artist_id": "rust", "title": "T", "description": "d",
                                 "tracks": [{"title": "one", "hash": "h9"}]}}
    album = heard_album_from_row(row, artist_name="Roan Patina", album_id="AFAR-0009")
    assert album.artist_id == "rust"
    assert album.album_id == "AFAR-0009"
    assert album.tracks[0].content_hash == "h9"
