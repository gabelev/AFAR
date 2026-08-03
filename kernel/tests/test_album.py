"""The album contract: what an artist may hand back, and what is rejected."""

from __future__ import annotations

import json

import pytest

from afar.album import MAX_TRACKS, Album, AlbumTrack
from afar.config import _MOCK_INTENTS
from afar.intent import Intent


def _intent(player_id: str = "silt", **over: object) -> Intent:
    payload = dict(_MOCK_INTENTS[player_id])
    payload.update(over)
    return Intent.from_json(json.dumps(payload))


def _reply(artist_id: str = "silt", n: int = 3, **over: object) -> str:
    body = {
        "title": "Standpipe",
        "description": "Three takes cut in one afternoon, all of them wet.",
        "rationale": "The rain never left the tape.",
        "tracks": [
            {
                "title": f"Track {i}",
                "note": f"note {i}",
                "intent": {**_MOCK_INTENTS[artist_id], "lyrics": f"words {i}"},
            }
            for i in range(n)
        ],
    }
    body.update(over)
    return json.dumps(body)


def _album(artist_id: str = "silt", n: int = 3) -> Album:
    return Album.from_json(_reply(artist_id, n), artist_id=artist_id)


def test_parses_a_whole_album_from_one_reply() -> None:
    album = _album()
    assert album.title == "Standpipe"
    assert [t.title for t in album.tracks] == ["Track 0", "Track 1", "Track 2"]
    assert album.tracks[0].lyrics == "words 0"
    assert album.rationale == "The rain never left the tape."


def test_tolerates_fences_and_prose_like_intent_does() -> None:
    fenced = "Here it is:\n```json\n" + _reply() + "\n```\n"
    assert Album.from_json(fenced, artist_id="silt").title == "Standpipe"


def test_artist_id_is_a_fact_of_the_session_not_the_reply() -> None:
    """Who is recording is stamped by the caller — a model cannot claim it."""
    reply = json.loads(_reply("silt"))
    for track in reply["tracks"]:
        track["intent"]["player_id"] = "rust"
    album = Album.from_json(json.dumps(reply), artist_id="silt")
    assert album.artist_id == "silt"
    assert {t.intent.player_id for t in album.tracks} == {"silt"}


def test_the_note_is_the_one_thing_the_artist_says_about_a_song() -> None:
    """Given a note, it wins over the DNA's own line — one source, no drift."""
    album = _album()
    assert album.tracks[1].note == "note 1"
    assert album.tracks[1].intent.line == "note 1"


def test_a_track_with_no_note_keeps_the_line_from_its_dna() -> None:
    reply = json.loads(_reply())
    for track in reply["tracks"]:
        del track["note"]
    album = Album.from_json(json.dumps(reply), artist_id="silt")
    assert album.tracks[0].note == album.tracks[0].intent.line != ""


@pytest.mark.parametrize(
    "over, message",
    [
        ({"title": "  "}, "title must not be empty"),
        ({"description": ""}, "description must not be empty"),
    ],
)
def test_rejects_an_empty_sleeve(over: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Album.from_json(_reply(**over), artist_id="silt")


def test_rejects_a_single_and_an_anthology() -> None:
    with pytest.raises(ValueError, match="must carry"):
        Album.from_json(_reply(n=1), artist_id="silt")
    with pytest.raises(ValueError, match="must carry"):
        Album.from_json(_reply(n=MAX_TRACKS + 1), artist_id="silt")


def test_rejects_repeated_titles_on_one_sleeve() -> None:
    reply = json.loads(_reply())
    reply["tracks"][1]["title"] = reply["tracks"][0]["title"]
    with pytest.raises(ValueError, match="must differ from each other"):
        Album.from_json(json.dumps(reply), artist_id="silt")


def test_rejects_a_track_named_after_the_album() -> None:
    reply = json.loads(_reply())
    reply["tracks"][2]["title"] = "standpipe"
    with pytest.raises(ValueError, match="album title must differ"):
        Album.from_json(json.dumps(reply), artist_id="silt")


def test_rejects_a_track_with_no_dna() -> None:
    reply = json.loads(_reply())
    del reply["tracks"][0]["intent"]
    with pytest.raises(ValueError, match="missing its `intent`"):
        Album.from_json(json.dumps(reply), artist_id="silt")


def test_names_the_bad_track_when_its_dna_is_malformed() -> None:
    reply = json.loads(_reply())
    reply["tracks"][1]["intent"]["era"] = 99
    with pytest.raises(ValueError, match="'Track 1'"):
        Album.from_json(json.dumps(reply), artist_id="silt")


def test_content_hash_covers_the_words_and_the_dna() -> None:
    album = _album()
    same = _album()
    assert album.content_hash() == same.content_hash()

    retitled = Album(
        artist_id=album.artist_id,
        title="Other",
        description=album.description,
        tracks=album.tracks,
    ).validate()
    assert retitled.content_hash() != album.content_hash()

    relyriced = Album(
        artist_id=album.artist_id,
        title=album.title,
        description=album.description,
        tracks=(
            AlbumTrack(
                title=album.tracks[0].title,
                intent=_intent(lyrics="different words"),
                note=album.tracks[0].note,
            ),
            *album.tracks[1:],
        ),
    ).validate()
    assert relyriced.content_hash() != album.content_hash()


def test_to_row_carries_the_whole_record() -> None:
    row = _album().to_row()
    assert row["artist_id"] == "silt"
    assert row["content_hash"]
    assert len(row["tracks"]) == 3
    assert row["tracks"][0]["intent"]["sonicPalette"]
    assert row["tracks"][0]["lyrics"] == "words 0"
