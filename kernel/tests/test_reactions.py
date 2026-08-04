"""The staff react to a finished album — and change nothing.

Offline end to end (MockProvider). An album is written and PUBLISHED, then
`run_reactions` walks the five staff over it. Under test: the reactions run
only after publication, every stage lands as an appended `staff` row, a stage
that fails degrades alone and never touches the record, and none of the five
has a channel back to an artist — no cut, no veto, no title, no brief.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ensemble.providers.model import MockProvider

from afar.agents.archivist import ArchivistAgent
from afar.agents.critic import CriticAgent
from afar.agents.listener import ListenerAgent
from afar.agents.muse import MuseAgent
from afar.agents.producer import ProducerAgent
from afar.album import Album
from afar.config import AfarConfig, _MOCK_INTENTS, _mock_players
from afar.log import JsonlLedger, RunContext
from afar.render.base import MockRenderer
from afar.staff import (
    REACTION_DEGRADED_NOTES,
    load_reactions,
    load_recent_reactions,
    run_reactions,
)

_RUN_ID = "test-album-run"
_RELEASE_ID = "release-0008"

#: How each reaction's prompt is recognized (markers ride the prompt text, so
#: they survive the retry ladder's nudged re-prompts too).
_STAGE_MARKERS: dict[str, tuple[str, ...]] = {
    "producer": ("A record just came out",),
    "critic": ('"verdict"', "TRACKS:"),
    "muse": ("what the scene is doing",),
    "listener": ("A new record just dropped",),
    "archivist": ("Shelve this record",),
}


def _album(artist_id: str = "silt", n: int = 3) -> Album:
    reply = json.dumps(
        {
            "title": "Standpipe",
            "description": "Three songs cut in one afternoon, all of them wet.",
            "rationale": "The rain never left the tape.",
            "tracks": [
                {
                    "title": f"Song {i}",
                    "note": f"what I meant by song {i}",
                    "intent": {**_MOCK_INTENTS[artist_id], "lyrics": f"the words of {i}"},
                }
                for i in range(n)
            ],
        }
    )
    return Album.from_json(reply, artist_id=artist_id)


def _config(runs_root: Path, responder=_mock_players) -> AfarConfig:
    return AfarConfig(
        model=MockProvider(responder=responder),
        renderer=MockRenderer(runs_root / "audio"),
        runs_root=runs_root,
        live=False,
        code_sha="test-sha",
    )


def _failing(*stages: str, reply: str = ""):
    """A responder that PERSISTENTLY breaks the given reactions' model calls
    (empty reply by default) and stays the offline mock for everything else."""

    def responder(messages):
        text = "\n".join(m.content for m in messages)
        for stage in stages:
            if all(marker in text for marker in _STAGE_MARKERS[stage]):
                return reply
        return _mock_players(messages)

    return responder


@pytest.fixture
def published(tmp_path: Path) -> tuple[Album, Path]:
    """One album, published: its rows logged and its record file written.

    Stands in for the album spine's publish step (`run_album`) — the staff
    only ever see what it leaves behind: a record on disk and a release id.
    """
    album = _album()
    ledger = JsonlLedger(tmp_path, _RUN_ID, context=RunContext(code_sha="test-sha"))
    ledger.write(
        "releases",
        {"id": _RELEASE_ID, "kind": "album", "album_id": album.content_hash(), **album.to_row()},
    )
    run_dir = tmp_path / _RUN_ID
    (run_dir / f"release-{_RELEASE_ID}.json").write_text(
        json.dumps({"release_id": _RELEASE_ID, "album": album.to_row()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return album, run_dir


def _rows(run_dir: Path, table: str = "staff") -> list[dict]:
    path = run_dir / f"{table}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- the frame: after publication, appended, and harmless ----------------------


def test_reactions_run_after_publication_and_land_as_appended_rows(published):
    album, run_dir = published
    config = _config(run_dir.parent)
    before = {table: (run_dir / f"{table}.jsonl").read_text() for table in ("releases",)}
    record_before = (run_dir / f"release-{_RELEASE_ID}.json").read_text()

    result = run_reactions(album, run_dir=run_dir, config=config, release_id=_RELEASE_ID)

    # Every stage filed, in order, one row each, all stamped with what they
    # reacted to — and every row written AFTER the publication rows.
    rows = _rows(run_dir)
    assert [row["kind"] for row in rows] == [
        "producer_reaction",
        "album_review",
        "scene_note",
        "listener_reaction",
        "shelving",
    ]
    for row in rows:
        assert row["album_id"] == album.content_hash()
        assert row["release_id"] == _RELEASE_ID
        assert row["artist"] == "silt"
    assert not result.degraded

    # The material is untouched: the album's own rows and its published record
    # are byte-identical, and nothing else was written.
    for table, old in before.items():
        assert (run_dir / f"{table}.jsonl").read_text() == old
    assert (run_dir / f"release-{_RELEASE_ID}.json").read_text() == record_before
    assert sorted(p.name for p in run_dir.glob("*.jsonl")) == [
        "releases.jsonl",
        "staff.jsonl",
    ]

    # What came back: five reactions, and the album unchanged under them.
    assert result.album_id == album.content_hash()
    assert result.release_id == _RELEASE_ID
    assert result.producer.text and result.producer.who_for
    assert result.review.verdict
    assert set(result.review.track_notes) == {t.title for t in album.tracks}
    assert result.scene_note.body and result.scene_note.theme
    assert result.listener.valence in ("loved", "liked", "mixed", "cold")
    assert result.shelving.placement in ("companion", "standalone", "collection")
    assert result.shelving.notes


def test_reactions_refuse_to_run_before_publication(published):
    """The staff react to records that exist. With nothing published there is
    no path to a staff member at all — not even a degraded one."""
    album, run_dir = published
    config = _config(run_dir.parent)
    with pytest.raises(ValueError, match="PUBLISHED"):
        run_reactions(album, run_dir=run_dir, config=config, release_id="")
    assert _rows(run_dir) == []
    assert config.model.calls == []


def test_the_reaction_rows_are_a_publishable_block(published):
    album, run_dir = published
    result = run_reactions(
        album, run_dir=run_dir, config=_config(run_dir.parent), release_id=_RELEASE_ID
    )
    block = result.to_row()
    assert set(block) == {"producer", "critic", "muse", "listener", "archivist"}
    assert block["critic"]["track_notes"]
    assert block["archivist"]["liner_notes"]
    assert load_reactions(run_dir, album_id=album.content_hash()) == _rows(run_dir)
    assert load_reactions(run_dir, album_id="not-this-album") == []


def test_reactions_are_appended_never_edited(published):
    album, run_dir = published
    config = _config(run_dir.parent)
    run_reactions(album, run_dir=run_dir, config=config, release_id=_RELEASE_ID)
    first = (run_dir / "staff.jsonl").read_text()
    run_reactions(album, run_dir=run_dir, config=config, release_id=_RELEASE_ID)
    after = (run_dir / "staff.jsonl").read_text()
    assert after.startswith(first)
    assert len(_rows(run_dir)) == 10


# --- degradation: a failed reaction never touches the record -------------------


@pytest.mark.parametrize("stage", ["producer", "critic", "muse", "listener", "archivist"])
def test_one_failed_reaction_degrades_alone_and_changes_nothing(published, stage: str):
    album, run_dir = published
    config = _config(run_dir.parent, _failing(stage))
    record_before = (run_dir / f"release-{_RELEASE_ID}.json").read_text()
    album_rows_before = (run_dir / "releases.jsonl").read_text()
    hash_before = album.content_hash()

    result = run_reactions(album, run_dir=run_dir, config=config, release_id=_RELEASE_ID)

    assert result.degraded == (stage,)
    assert getattr(
        result,
        {
            "producer": "producer",
            "critic": "review",
            "muse": "scene_note",
            "listener": "listener",
            "archivist": "shelving",
        }[stage],
    ) is None
    # The honest row, in the same table as everything else.
    (failed,) = [r for r in _rows(run_dir) if r["kind"] == "staff_stage_failed"]
    assert failed["agent"] == stage and failed["error"]
    assert failed["note"] == REACTION_DEGRADED_NOTES[stage]
    # The other four still filed.
    assert len([r for r in _rows(run_dir) if r["kind"] != "staff_stage_failed"]) == 4
    # And the record is exactly as it was published.
    assert (run_dir / f"release-{_RELEASE_ID}.json").read_text() == record_before
    assert (run_dir / "releases.jsonl").read_text() == album_rows_before
    assert album.content_hash() == hash_before
    assert album.title == "Standpipe"
    assert [t.title for t in album.tracks] == ["Song 0", "Song 1", "Song 2"]


def test_every_reaction_failing_still_leaves_the_record_out(published):
    album, run_dir = published
    config = _config(
        run_dir.parent, _failing("producer", "critic", "muse", "listener", "archivist")
    )
    record_before = (run_dir / f"release-{_RELEASE_ID}.json").read_text()

    result = run_reactions(album, run_dir=run_dir, config=config, release_id=_RELEASE_ID)

    assert result.degraded == ("producer", "critic", "muse", "listener", "archivist")
    assert result.to_row() == {"degraded": dict(REACTION_DEGRADED_NOTES)}
    assert [r["kind"] for r in _rows(run_dir)] == ["staff_stage_failed"] * 5
    assert (run_dir / f"release-{_RELEASE_ID}.json").read_text() == record_before


# --- each reactor, and the channel it does not have ----------------------------


def test_the_producer_books_nothing(published):
    album, _ = published
    provider = MockProvider(responder=_mock_players)
    reaction = ProducerAgent(provider).react_to_album(album, artist_name="Delta Marlowe")

    assert reaction.text and reaction.who_for and reaction.what_it_does
    assert not hasattr(reaction, "duration_s") and not hasattr(reaction, "session_form")
    # ONE call, and nothing in it asks for a decision: no panel scores, no
    # take to choose, no session to book, no instruction to the artist.
    assert len(provider.calls) == 1
    text = "\n".join(m.content for m in provider.calls[0])
    assert "You had no hand in this record" in text
    for forbidden in ('"scores"', "ROUNDS:", "session_form", "duration_s", "the cut"):
        assert forbidden not in text


def test_the_critic_names_nothing(published):
    album, _ = published
    provider = MockProvider(responder=_mock_players)
    review = CriticAgent(provider).review_album(album, artist_name="Delta Marlowe")

    # It reviews under the artist's own titles, and returns no title of its own.
    assert set(review.track_notes) == {t.title for t in album.tracks}
    assert not hasattr(review, "release_title") and not hasattr(review, "take_titles")
    text = "\n".join(m.content for m in provider.calls[0])
    assert "YOU NAME NOTHING" in text
    assert "never propose a better one" in text
    assert album.title in text and album.tracks[0].lyrics in text
    for forbidden in ("release_title", "Write its sleeve", "THE TRACEABILITY LAW"):
        assert forbidden not in text


def test_the_critic_refuses_a_review_that_skips_a_song(published):
    album, _ = published

    def half_a_review(messages):
        text = "\n".join(m.content for m in messages)
        if '"verdict"' in text and "TRACKS:" in text:
            return json.dumps({"verdict": "Holds.", "tracks": {"Song 0": "fine"}})
        return _mock_players(messages)

    with pytest.raises(ValueError, match="critic/album-review"):
        CriticAgent(MockProvider(responder=half_a_review)).review_album(album)


def test_the_muse_briefs_no_one(published):
    album, run_dir = published
    provider = MockProvider(responder=_mock_players)
    note = MuseAgent(provider).read_scene(albums=[album], stance="porous")

    # What the note carries: a theme that precipitated, and where it came from.
    assert note.body and note.theme
    assert note.thin is True  # no perceiver wired here: an honest, thin note
    # What it does NOT carry: instructions. Palette notes and forbidden moves
    # only ever served the brief, and the brief is gone.
    assert not hasattr(note, "palette_notes") and not hasattr(note, "forbidden_moves")
    text = "\n".join(m.content for m in provider.calls[0])
    assert "It is not a brief" in text
    assert "do not hand anyone an instruction" in text
    for forbidden in ("palette_notes", "FORBIDDEN MOVES", "what to reach for next"):
        assert forbidden not in text


def test_the_muse_reads_the_scan_and_the_record(published):
    album, _ = published

    class _Scan:
        def broad_scan(self, queries, cycle_id=""):
            from ensemble.perceive import Evidence

            return [
                Evidence(
                    title="basement tape revival keeps spreading",
                    url="https://example.test/basement",
                    published="2026-08-01",
                    summary="Cheap rooms, one microphone, no apology.",
                )
            ]

    provider = MockProvider(responder=_mock_players)
    note = MuseAgent(provider, perceiver=_Scan()).read_scene(albums=[album])
    text = "\n".join(m.content for m in provider.calls[0])
    assert note.thin is False
    assert "basement tape revival" in text  # the field
    assert album.title in text  # and what this world just put out


def test_a_dead_scan_makes_a_thin_note_not_a_dead_stage(published):
    album, _ = published

    class _Broken:
        def broad_scan(self, queries, cycle_id=""):
            raise RuntimeError("the network is gone")

    note = MuseAgent(MockProvider(responder=_mock_players), perceiver=_Broken()).read_scene(
        albums=[album]
    )
    assert note.thin is True and note.body


def test_the_listener_reads_the_critic_but_owes_it_nothing(published):
    album, _ = published
    provider = MockProvider(responder=_mock_players)
    reaction = ListenerAgent(provider).react_to_album(
        album, critic_verdict="The record holds. It is not trying to be liked."
    )
    assert reaction.valence in ("loved", "liked", "mixed", "cold")
    text = "\n".join(m.content for m in provider.calls[0])
    assert "It is not trying to be liked" in text
    assert "you owe it nothing" in text

    cold = ListenerAgent(MockProvider(responder=_mock_players)).react_to_album(album)
    assert cold.text  # a degraded Critic just means the fan heard it cold


def test_the_archivist_does_not_retitle(published):
    album, _ = published
    provider = MockProvider(responder=_mock_players)
    shelving = ArchivistAgent(provider).shelve_album(album, artist_name="Delta Marlowe")

    # Structurally impossible: there is no title on what it returns.
    assert not hasattr(shelving, "tape_title") and not hasattr(shelving, "title")
    assert shelving.placement in ("companion", "standalone", "collection")
    assert shelving.notes
    text = "\n".join(m.content for m in provider.calls[0])
    assert "THE RECORD IS ALREADY NAMED" in text
    assert "never write a title of your own" in text
    assert "tape_title" not in text


def test_the_archivist_can_only_call_out_songs_that_exist(published):
    album, _ = published

    def invents_a_song(messages):
        text = "\n".join(m.content for m in messages)
        if "Shelve this record" in text:
            return json.dumps(
                {
                    "placement": "standalone",
                    "arc": "Opens plain.",
                    "callouts": [
                        {"song": "Song 1", "note": "the one that turns"},
                        {"song": "A Song That Is Not On It", "note": "invented"},
                    ],
                    "liner_notes": "Shelved where it can be found.",
                }
            )
        return _mock_players(messages)

    shelving = ArchivistAgent(MockProvider(responder=invents_a_song)).shelve_album(album)
    assert [c["song"] for c in shelving.callouts] == ["Song 1"]


# --- the reception loop: public, logged, and pointed at nobody -----------------


def test_the_fans_word_reaches_the_muse_through_the_log(published, tmp_path: Path):
    """The Listener's logged reaction is read by the Muse's next note — staff
    prose reaching staff prose, in public, through the log. It reaches no
    artist: the album's own writing is long over by then."""
    album, run_dir = published
    config = _config(run_dir.parent)
    run_reactions(album, run_dir=run_dir, config=config, release_id=_RELEASE_ID)

    rows = load_recent_reactions(run_dir.parent)
    assert [row["kind"] for row in rows] == ["listener_reaction"]
    assert rows[0]["valence"] in ("loved", "liked", "mixed", "cold")
    assert load_recent_reactions(run_dir.parent, exclude_run=_RUN_ID) == []

    # A second album's Muse sees it.
    other = _album("rust")
    other_dir = tmp_path / "test-album-run-b"
    JsonlLedger(tmp_path, other_dir.name, context=RunContext(code_sha="test-sha")).write(
        "releases", {"id": "release-0009", "kind": "album", **other.to_row()}
    )
    provider = MockProvider(responder=_mock_players)
    config_b = AfarConfig(
        model=provider,
        renderer=MockRenderer(tmp_path / "audio"),
        runs_root=tmp_path,
        live=False,
        code_sha="test-sha",
    )
    run_reactions(other, run_dir=other_dir, config=config_b, release_id="release-0009")
    muse_calls = [
        "\n".join(m.content for m in call)
        for call in provider.calls
        if any("what the scene is doing" in m.content for m in call)
    ]
    assert muse_calls
    assert rows[0]["text"] in muse_calls[-1]


def test_no_reaction_can_fill_a_direction_frame(published):
    """The staff→artist channel that used to exist was a DIRECTION: a hard
    whitelist of four fields (text / palette_notes / forbidden_moves /
    duration_s) that rode from the Muse's brief through the Producer into a
    player's context. No live reaction carries the instruction half of that
    shape — there is nothing on the staff side left to offer."""
    from afar.perception.context import DIRECTION_FRAME_KEYS

    album, run_dir = published
    result = run_reactions(
        album, run_dir=run_dir, config=_config(run_dir.parent), release_id=_RELEASE_ID
    )
    instructions = tuple(k for k in DIRECTION_FRAME_KEYS if k != "text") + (
        "session_form",
        "stance_note",
    )
    for reaction in (
        result.producer,
        result.review,
        result.scene_note,
        result.listener,
        result.shelving,
    ):
        for key in instructions:
            assert not hasattr(reaction, key), f"{type(reaction).__name__}.{key}"
    for row in _rows(run_dir):
        assert not set(row) & set(instructions)
