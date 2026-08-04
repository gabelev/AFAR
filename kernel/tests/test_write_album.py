"""Player.write_album: one call, the artist's own voice, a whole record.

The prompt is the product here — the laws it carries are the reason the
architecture changed (docs/SPEC.md, DECISIONS 2026-08-03) — so these tests pin
what the call is made of as well as what it returns.
"""

from __future__ import annotations

import json

import pytest
from ensemble.providers.model import Message, MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.album import Album
from afar.config import _MOCK_INTENTS, _mock_players
from afar.perception.album_context import HeardAlbum, HeardTrack, build_album_context
from afar.render.base import MockRenderer


def _player(tmp_path, responder=_mock_players, pid: str = "silt") -> Player:
    model = MockProvider(responder=responder)
    return Player(PERSONAS[pid], model, MockRenderer(tmp_path / "audio"))


def _album_reply(artist_id: str = "silt", n: int = 3) -> str:
    return json.dumps(
        {
            "title": "The Tide Line",
            "description": "Three songs recorded under the mark the flood left.",
            "rationale": "The room is full again.",
            "tracks": [
                {
                    "title": f"Silt Course {i}",
                    "note": f"song {i} keeps the floor",
                    "intent": {**_MOCK_INTENTS[artist_id], "lyrics": f"words {i}"},
                }
                for i in range(n)
            ],
        }
    )


def _context(**over):
    heard = [
        HeardAlbum(
            artist_id="rust",
            title="Oxide in the Joist",
            description="Four takes left outdoors.",
            tracks=(HeardTrack(title="Standpipe", note="I kept the hiss.", content_hash="h1"),),
            artist_name="Roan Patina",
            album_id="AFAR-0002",
        )
    ]
    return build_album_context("silt", heard=heard, **over)


# --- the call ------------------------------------------------------------------


def test_one_model_call_returns_a_whole_validated_record(tmp_path):
    player = _player(tmp_path)
    album = player.write_album(_context(), n_tracks=3, duration_s=45)
    assert isinstance(album, Album)
    assert album.artist_id == "silt"
    assert album.title and album.description
    assert len(album.tracks) == 3
    assert len(player.model.calls) == 1
    for track in album.tracks:
        assert track.title and track.note and track.lyrics
        assert track.intent.player_id == "silt"


def test_the_system_message_is_the_persona_prompt_unchanged(tmp_path):
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=2, duration_s=30)
    system, user = player.model.calls[0]
    assert system.role == "system"
    assert system.content == PERSONAS["silt"].base_prompt
    assert user.role == "user"


def test_the_user_message_carries_the_laws_of_the_record(tmp_path):
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=3, duration_s=45)
    prompt = player.model.calls[0][1].content
    # traceable to who you are and what you have heard
    assert "who you are, and what you have heard" in prompt
    # the title is written WITH the songs
    assert "written WITH the songs, not after" in prompt
    # nothing named in isolation
    assert "Nothing is named in isolation" in prompt
    # the songs are written to the album
    assert "the songs are written to it" in prompt
    # the artist names its own work
    assert "You name your own work" in prompt


def test_the_absorption_law_is_in_the_prompt(tmp_path):
    """What you heard changes what you make; it never becomes what you make it
    about. The first live sleeves annotated the listening instead of being
    changed by it ("Evers plays four chords back to the top. I pulled the
    fourth") — a reply, not a record. This law is what forbids that."""
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=3, duration_s=45)
    prompt = player.model.calls[0][1].content
    assert "CHANGES WHAT YOU MAKE" in prompt
    assert "never becomes what you make it ABOUT" in prompt
    # the ban, named field by field
    assert "never name another artist" in prompt
    assert "never quote or describe their songs or their titles" in prompt
    for framing in ("answering", "replying to", "rebutting", "correcting"):
        assert framing in prompt
    assert "No commentary on the scene" in prompt
    assert "sleeve about the record next door" in prompt
    # and what absorption looks like instead
    assert "reach for something you would not have reached for" in prompt
    assert "do not narrate the transaction" in prompt


def test_the_public_sleeve_and_the_private_rationale_are_split_in_the_prompt(tmp_path):
    """The influence stays auditable: the log still shows what the artist
    considered, the record just does not announce it."""
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=3, duration_s=45)
    prompt = player.model.calls[0][1].content
    assert "PUBLIC (it goes on the sleeve" in prompt
    assert "PRIVATE (logged, never printed)" in prompt
    assert '"title": PUBLIC' in prompt
    assert '"description": PUBLIC' in prompt
    assert '"rationale": PRIVATE' in prompt
    assert '"note": PUBLIC' in prompt
    # the rationale is named as the place the hearing goes
    assert "The hearing goes in the RATIONALES" in prompt
    assert "this is where what you heard belongs" in prompt.lower()


def test_the_heard_block_says_it_is_not_a_subject(tmp_path):
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=3, duration_s=45)
    prompt = player.model.calls[0][1].content
    assert "not to give you a subject" in prompt
    assert "may appear anywhere on your sleeve" in prompt


def test_the_material_the_artist_hears_is_not_weakened_by_the_law(tmp_path):
    """Only what may be WRITTEN changed — what reaches the artist did not."""
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=3, duration_s=45)
    prompt = player.model.calls[0][1].content
    assert 'Roan Patina — "Oxide in the Joist"' in prompt
    assert "Four takes left outdoors." in prompt
    assert '1. "Standpipe" — I kept the hiss.' in prompt


def test_the_prompt_shows_the_sleeves_of_what_was_heard(tmp_path):
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=2, duration_s=30)
    prompt = player.model.calls[0][1].content
    assert 'Roan Patina — "Oxide in the Joist"' in prompt
    assert "Four takes left outdoors." in prompt
    assert '1. "Standpipe" — I kept the hiss.' in prompt


def test_measured_facts_are_rendered_under_the_song_they_describe(tmp_path):
    heard = HeardAlbum(
        artist_id="rust",
        title="Oxide in the Joist",
        description="d",
        tracks=(HeardTrack(title="Standpipe", note="n", content_hash="h1"),),
        artist_name="Roan Patina",
    ).with_heard(
        {
            "h1": {
                "tempo_bpm": 98.0,
                "loudness": "quiet",
                "brightness": "dark",
                "duration_s": 45.0,
                "moved": "away_from_you",
            }
        }
    )
    player = _player(tmp_path)
    player.write_album(build_album_context("silt", heard=[heard]), n_tracks=2, duration_s=30)
    prompt = player.model.calls[0][1].content
    assert (
        "how it sounded to you: about 98 BPM, quiet, dark, 45 seconds, "
        "it moved away from yours, closer to their own last one" in prompt
    )
    assert "trust those over what the sleeve claims" in prompt


def test_an_isolated_artist_is_told_it_heard_nothing(tmp_path):
    player = _player(tmp_path)
    player.write_album(_context(isolated=True), n_tracks=2, duration_s=30)
    prompt = player.model.calls[0][1].content
    assert "Nobody else's music has reached you" in prompt
    assert "Oxide in the Joist" not in prompt


def test_the_artists_own_last_record_is_shown_as_its_own_block(tmp_path):
    own = HeardAlbum(
        artist_id="silt",
        title="Tide Line",
        description="Everything kept.",
        tracks=(HeardTrack(title="Under the Plaster", note="still ringing"),),
        artist_name="Delta Marlowe",
    )
    player = _player(tmp_path)
    player.write_album(_context(own_last=own), n_tracks=2, duration_s=30)
    prompt = player.model.calls[0][1].content
    assert "YOUR LAST RECORD:" in prompt
    assert '"Tide Line"' in prompt


def test_lyric_guidance_scales_with_the_take_length(tmp_path):
    short = _player(tmp_path)
    short.write_album(_context(), n_tracks=2, duration_s=30)
    long_ = _player(tmp_path)
    long_.write_album(_context(), n_tracks=2, duration_s=120)
    assert "about 8 lines (~45 words)" in short.model.calls[0][1].content
    assert "about 24 lines (~180 words)" in long_.model.calls[0][1].content


def test_the_prompt_states_the_size_of_the_record_machine_readably(tmp_path):
    player = _player(tmp_path)
    player.write_album(_context(), n_tracks=4, duration_s=60)
    prompt = player.model.calls[0][1].content
    assert "TRACKS: 4" in prompt
    assert "SECONDS PER TRACK: 60" in prompt


def test_drift_reaches_the_album_call_when_it_exists(tmp_path):
    player = _player(tmp_path)
    player.self_state.residue.update({"era": 2, "stance": "hostile"})
    player.self_state.obsessions.extend(["sediment", "the tide line"])
    player.write_album(_context(), n_tracks=2, duration_s=30)
    prompt = player.model.calls[0][1].content
    assert "WHERE YOU ARE NOW: Era 2, stance hostile." in prompt
    assert "You keep returning to: sediment, the tide line." in prompt


# --- the retry ladder ----------------------------------------------------------


def test_an_empty_reply_is_simply_asked_again(tmp_path):
    replies = iter(["", _album_reply()])

    player = _player(tmp_path, responder=lambda _m: next(replies))
    album = player.write_album(_context(), n_tracks=3, duration_s=30)
    assert album.title == "The Tide Line"
    assert len(player.model.calls) == 2


def test_a_malformed_reply_gets_one_nudged_re_prompt(tmp_path):
    replies = iter(["not json at all", _album_reply()])

    player = _player(tmp_path, responder=lambda _m: next(replies))
    album = player.write_album(_context(), n_tracks=3, duration_s=30)
    assert len(album.tracks) == 3
    assert len(player.model.calls) == 2
    nudge = player.model.calls[1][-1].content
    assert "ONLY the album JSON object" in nudge


def test_a_record_that_never_parses_raises_rather_than_shipping_junk(tmp_path):
    player = _player(tmp_path, responder=lambda _m: "still not json")
    with pytest.raises(ValueError, match="album:silt"):
        player.write_album(_context(), n_tracks=3, duration_s=30)


def test_the_wrong_number_of_songs_is_re_prompted_because_it_is_the_budget(tmp_path):
    replies = iter([_album_reply(n=5), _album_reply(n=3)])

    player = _player(tmp_path, responder=lambda _m: next(replies))
    album = player.write_album(_context(), n_tracks=3, duration_s=30)
    assert len(album.tracks) == 3
    assert "this record is 3 songs, not 5" in player.model.calls[1][-1].content


def test_an_album_size_outside_the_contract_is_refused_before_any_model_call(tmp_path):
    player = _player(tmp_path)
    with pytest.raises(ValueError, match="2-6 tracks"):
        player.write_album(_context(), n_tracks=9, duration_s=30)
    assert player.model.calls == []


def test_the_artist_id_is_the_sessions_fact_not_the_models_claim(tmp_path):
    """A reply whose per-track player_id says someone else still lands as this
    artist's record — who is recording is decided by the caller."""
    lying = json.dumps(
        {
            "title": "The Tide Line",
            "description": "d",
            "tracks": [
                {
                    "title": f"Song {i}",
                    "note": "n",
                    "intent": {**_MOCK_INTENTS["silt"], "player_id": "rust"},
                }
                for i in range(2)
            ],
        }
    )
    player = _player(tmp_path, responder=lambda _m: lying)
    album = player.write_album(_context(), n_tracks=2, duration_s=30)
    assert album.artist_id == "silt"
    assert {t.intent.player_id for t in album.tracks} == {"silt"}


def test_the_offline_mock_answers_the_record_it_was_asked_for(tmp_path):
    """The mock voice is what every offline run and test depends on: it must
    honour the size the conductor budgeted."""
    for n in (2, 4, 6):
        player = _player(tmp_path)
        album = player.write_album(_context(), n_tracks=n, duration_s=30)
        assert len(album.tracks) == n


def test_the_per_round_decide_path_still_works(tmp_path):
    """The experiment instrument is not collateral damage."""
    from ensemble.agent import Perception

    player = _player(tmp_path)
    decision = player.decide(Perception(data={"round": 0, "others": []}))
    assert decision.data["intent"].player_id == "silt"
