"""THE acceptance for the loop: book -> make -> publish -> the staff react.

Everything offline (MockProvider + MockRenderer + MockEmbedder, publish
forced dry or against a recording fake connection). What this file is for:

- the LOOP walks a whole record end to end and logs every step;
- the BUDGET is charged before the first render and blocks a record it
  cannot afford;
- the ORDER is publish-then-react, which is architecture rule 1 in the call
  graph rather than in a comment;
- what an artist HEARS is sleeve text and measured facts, never a staff word,
  even when the row it came from is full of them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ensemble.providers.model import MockProvider

from afar import album_log
from afar.album import MIN_TRACKS
from afar.config import AfarConfig, _mock_players
from afar.conductor import Conductor, next_album_index
from afar.perception.embedder import MockEmbedder
from afar.publish import (
    build_album_row,
    build_album_track_rows,
    next_catalogue_id,
    publish_album,
    reactions_from_rows,
)
from afar.render.base import MockRenderer


def _config(root: Path, *, minutes: float = 110.0, tracks: int = 2, seconds: int = 30):
    return AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=MockRenderer(root / "audio"),
        runs_root=root,
        live=False,
        code_sha="test-sha",
        enabled=True,
        asks_per_day=8.0,
        album_tracks=tracks,
        track_seconds=seconds,
        daily_audio_minutes=minutes,
    )


def _conductor(root: Path, **kw) -> Conductor:
    return Conductor(_config(root, **kw), embedder=MockEmbedder())


def _booking(conductor: Conductor, index: int = 0, minutes: float | None = None, artist: str | None = None):
    """What the conductor builds once an artist has said yes: the affordable
    size plus the mechanical half (clock position, seed, run id)."""
    size = conductor.affordable(
        conductor.budget.remaining_minutes if minutes is None else minutes
    )
    if size is None:
        return None
    return conductor.plan_record(artist or conductor.roster[0], index, size)


def _rows(root: Path) -> list[dict]:
    path = root / "conductor" / "conductor.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- the loop, end to end -----------------------------------------------------


def test_one_booked_album_walks_the_whole_chain(tmp_path: Path):
    conductor = _conductor(tmp_path)
    booking = _booking(conductor)
    assert booking is not None
    outcome = conductor.run_one_album(booking)

    assert outcome.completed and outcome.artist_id == booking.artist_id
    assert outcome.title and outcome.album_id

    kinds = [r["kind"] for r in _rows(tmp_path)]
    assert kinds.index("album_booked") < kinds.index("album_published")
    # PUBLISH BEFORE REACTIONS: run_reactions refuses a record that is not out.
    assert kinds.index("album_published") < kinds.index("reactions_published")

    run_dir = tmp_path / booking.run_id
    logged = [json.loads(l) for l in (run_dir / "albums.jsonl").read_text().splitlines()]
    assert len(logged) == 1
    record = logged[0]["record"]
    assert record["artist_id"] == booking.artist_id
    assert len(record["tracks"]) == booking.size.tracks
    # Every reaction landed as its own staff row, and none of them rewrote the
    # record: the album row is still exactly the one run_album logged.
    staff = [json.loads(l) for l in (run_dir / "staff.jsonl").read_text().splitlines()]
    assert {r["kind"] for r in staff} >= {"producer_reaction", "album_review", "shelving"}
    reread = [json.loads(l) for l in (run_dir / "albums.jsonl").read_text().splitlines()]
    assert len(reread) == 1 and reread[0]["record"] == record


def test_the_cursor_resumes_past_completed_and_failed_records():
    assert next_album_index([]) == 0
    assert next_album_index([{"kind": "album_completed", "album_index": 0}]) == 1
    assert (
        next_album_index(
            [
                {"kind": "album_completed", "album_index": 0},
                {"kind": "album_failed", "album_index": 1},
                {"kind": "album_booked", "album_index": 2},  # opened, never closed
            ]
        )
        == 2
    )


# --- the money ----------------------------------------------------------------


def test_the_whole_record_is_charged_before_the_first_render(tmp_path: Path):
    """A crash mid-record must never leave spend uncounted — the safe
    direction to be wrong in is 'already paid for'."""
    conductor = _conductor(tmp_path, tracks=3, seconds=60)
    booking = _booking(conductor)
    charged: list[float] = []

    def exploding(artist_id: str):
        charged.append(conductor.budget.spent_minutes)
        raise RuntimeError("the renderer fell over")

    conductor.artist = exploding
    with pytest.raises(RuntimeError):
        conductor.run_one_album(booking)
    assert charged == [pytest.approx(3.0)]  # 3 x 60s, charged up front
    assert conductor.budget.spent_minutes == pytest.approx(3.0)


def test_a_day_with_nothing_left_asks_nobody_at_all(tmp_path: Path):
    """A yes the conductor could not honour would be a lie — so on a spent day
    nobody is even asked."""
    conductor = _conductor(tmp_path, minutes=0.5)  # below the 1-minute floor
    assert conductor.affordable(conductor.budget.remaining_minutes) is None


def test_the_last_record_of_a_day_is_shrunk_not_skipped(tmp_path: Path):
    conductor = _conductor(tmp_path, tracks=4, seconds=120)
    booking = _booking(conductor, minutes=2.0)
    assert booking is not None and booking.minutes <= 2.0
    assert booking.size.tracks >= MIN_TRACKS


def test_a_failed_record_takes_the_short_backoff_then_paces_again(tmp_path: Path):
    from afar.conductor import AlbumOutcome

    conductor = _conductor(tmp_path)
    outcomes = iter(["fail", "fail", "ok"])

    def fake_run_one_album(booking):
        if next(outcomes) == "fail":
            raise RuntimeError("ElevenLabs music request failed (500)")
        return AlbumOutcome(
            index=booking.index,
            run_id=booking.run_id,
            artist_id=booking.artist_id,
            completed=True,
        )

    idles: list[tuple[float, dict]] = []

    def fake_idle(seconds: float, kind: str, **row) -> None:
        idles.append((seconds, row))
        if len(idles) >= 3:
            conductor._stop = True

    conductor.run_one_album = fake_run_one_album
    conductor._idle = fake_idle
    assert conductor.run_forever() == 0

    assert idles[0][0] == 900.0 and idles[0][1]["waiting"] == "failure_backoff"
    assert idles[1][0] == 1800.0
    assert idles[2][1]["waiting"] == "pace"
    rows = _rows(tmp_path)
    assert [r["consecutive_failures"] for r in rows if r["kind"] == "album_failed"] == [1, 2]
    assert conductor.album_index == 3  # a failed record still advances the clock


def test_sigterm_between_records_exits_cleanly(tmp_path: Path):
    conductor = _conductor(tmp_path)
    conductor._stop = True
    assert conductor.run_forever() == 0
    assert [r["kind"] for r in _rows(tmp_path)][-1] == "stopped"


# --- the law: what reaches the artist -----------------------------------------


def _album_row_with_staff_prose(artist_id: str) -> dict:
    """A logged album row with the staff's whole apparatus bolted onto it —
    the shape a republished, reacted-to record has."""
    return {
        "player": artist_id,
        "id": "hash-1",
        "record": {
            "album_id": "hash-1",
            "artist_id": artist_id,
            "album": {
                "artist_id": artist_id,
                "title": "Oxide in the Joist",
                "description": "Four takes left outdoors for a season.",
                "rationale": "PRIVATE: what reached me and what I did with it.",
                "tracks": [
                    {"title": "Standpipe", "note": "I kept the hiss.", "lyrics": "…"},
                ],
            },
            "tracks": [
                {"index": 0, "title": "Standpipe", "note": "I kept the hiss.", "hash": "abc123"}
            ],
            "heard": [],
            "features": {},
            # everything below is commentary and must not cross
            "staff": {
                "critic": {"verdict": "A cold, unfair verdict."},
                "producer": {"text": "The room's reaction."},
                "muse": {"text": "What the scene is doing."},
                "listener": {"text": "Played it twice."},
                "archivist": {"liner_notes": "Back of the sleeve."},
            },
        },
    }


def test_a_row_full_of_staff_prose_reaches_the_artist_as_sleeve_only():
    rows = [_album_row_with_staff_prose("rust")]
    heard, own_last = album_log.heard_for(rows, "silt", names={"rust": "Roan Patina"})
    assert own_last is None and len(heard) == 1
    context = heard[0].to_context()
    assert set(context) == {
        "artist_id", "artist_name", "album_id", "title", "description", "tracks"
    }
    blob = json.dumps(context)
    for staff_word in (
        "unfair verdict",
        "room's reaction",
        "the scene is doing",
        "Played it twice",
        "Back of the sleeve",
        "PRIVATE",
    ):
        assert staff_word not in blob
    assert context["tracks"] == [
        {"title": "Standpipe", "note": "I kept the hiss.", "content_hash": "abc123"}
    ]


def _row(artist_id: str, album_id: str, title: str) -> dict:
    return {
        "player": artist_id,
        "id": album_id,
        "record": {
            "album_id": album_id,
            "artist_id": artist_id,
            "album": {
                "artist_id": artist_id,
                "title": title,
                "description": "d",
                "tracks": [],
            },
            "tracks": [],
        },
    }


def test_an_artist_hears_others_newest_records_and_its_own_last():
    rows = [
        _row("rust", "r1", "First"),
        _row("silt", "s1", "Mine"),
        _row("rust", "r2", "Second"),
    ]
    heard, own_last = album_log.heard_for(rows, "silt")
    # One record per other artist: rust's NEWEST, not its back catalogue.
    assert [a.album_id for a in heard] == ["r2"]
    assert own_last is not None and own_last.album_id == "s1"


def test_the_heard_set_is_capped_so_one_prompt_stays_readable():
    rows = [_row(f"a{i}", f"x{i}", f"Record {i}") for i in range(9)]
    heard, _ = album_log.heard_for(rows, "silt", limit=4)
    assert len(heard) == 4
    assert [a.artist_id for a in heard] == ["a5", "a6", "a7", "a8"]


def test_the_ears_carry_measured_facts_the_context_never_does(tmp_path: Path):
    """The runner's measurements join the log by artifact hash and stay OUT of
    the sleeve: `Ears` is what the instruments recorded, the context is what
    the artist reads."""
    conductor = _conductor(tmp_path)
    first = _booking(conductor, minutes=110.0)
    conductor.run_one_album(first)

    rows = album_log.album_rows(tmp_path)
    listener = next(a for a in conductor.roster if a != first.artist_id)
    heard, _ = album_log.heard_for(rows, listener)
    ears = album_log.build_ears(tmp_path, rows, listener, heard)

    hashes = {t.content_hash for a in heard for t in a.tracks}
    assert hashes and hashes <= set(ears.audio)
    assert hashes <= set(ears.space("audio")) and hashes <= set(ears.space("intent"))
    assert all(path.is_file() for path in ears.audio.values())
    # A maker's own previous position exists only once they have two records.
    assert ears.maker_past.get("audio", {}) == {}


# --- publish ------------------------------------------------------------------


def test_album_ids_continue_the_one_afar_sequence_across_both_tables():
    assert next_catalogue_id(["0001", "0007"], []) == "0008"
    assert next_catalogue_id(["0001", "0007"], ["0008"]) == "0009"
    assert next_catalogue_id([], ["0008", "0011"]) == "0012"
    assert next_catalogue_id([], []) == "0001"


def test_the_album_row_puts_the_artist_and_their_own_words_first(tmp_path: Path):
    conductor = _conductor(tmp_path)
    booking = _booking(conductor, minutes=110.0)
    conductor.run_one_album(booking)
    run_dir = tmp_path / booking.run_id
    record = json.loads(sorted(run_dir.glob("album-*.json"))[0].read_text())

    row = build_album_row("0008", record, run_dir.name)
    assert row["id"] == "0008" and row["kind"] == "album"
    assert row["artistId"] == booking.artist_id  # attribution is a field, not a guess
    assert row["description"] == record["album"]["description"]
    assert row["title"] == record["album"]["title"]
    assert row["trackIds"] == [f"0008-{i + 1:02d}" for i in range(booking.size.tracks)]
    assert row["date"].startswith(run_dir.name[:4])
    # No staff prose on a record nobody has reacted to yet.
    assert "review" not in row and "linerNotes" not in row

    tracks = build_album_track_rows("0008", record, run_dir.name)
    assert [t["agentId"] for t in tracks] == [booking.artist_id] * booking.size.tracks
    assert all(t["durationSec"] == booking.size.track_seconds for t in tracks)
    assert all(t["audioUrl"].startswith("/api/media/") for t in tracks)


def test_reactions_are_additive_and_never_rewrite_the_record(tmp_path: Path):
    from afar.staff import load_reactions

    conductor = _conductor(tmp_path)
    booking = _booking(conductor, minutes=110.0)
    conductor.run_one_album(booking)
    run_dir = tmp_path / booking.run_id
    record = json.loads(sorted(run_dir.glob("album-*.json"))[0].read_text())

    bare = build_album_row("0008", record, run_dir.name)
    reactions = reactions_from_rows(load_reactions(run_dir, album_id=record["album_id"]))
    reacted = build_album_row("0008", record, run_dir.name, reactions=reactions)

    for field in ("id", "title", "artistId", "description", "trackIds", "era", "date"):
        assert reacted[field] == bare[field], f"a reaction changed {field}"
    assert reacted["review"] and reacted["reaction"] and reacted["linerNotes"]
    assert reacted["reactionValence"] in {"loved", "liked", "mixed", "cold"}


def test_a_degraded_stage_leaves_an_honest_note_and_no_prose():
    row = build_album_row(
        "0008",
        {
            "artist_id": "rust",
            "album": {"title": "T", "description": "D", "tracks": []},
            "tracks": [],
            "heard": [],
            "features": {},
        },
        "20260804-120000-album-0000-rust",
        reactions={"degraded": {"critic": "The Critic did not file on this record."}},
    )
    assert "review" not in row
    assert row["staffDegraded"] == {"critic": "The Critic did not file on this record."}


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    """Recording stand-in for a psycopg connection (jsonb passed raw)."""

    def __init__(self, releases: dict, albums: dict | None = None):
        self.releases = dict(releases)
        self.albums = dict(albums or {})
        self.tracks: dict[str, dict] = {}
        self.executed: list[tuple[str, tuple | None]] = []
        self.committed = False

    def execute(self, sql: str, params=None):
        self.executed.append((sql, params))
        if sql.startswith("SELECT id FROM releases"):
            return _FakeCursor([(i,) for i in self.releases])
        if sql.startswith("SELECT id FROM albums"):
            return _FakeCursor([(i,) for i in self.albums])
        if sql.startswith("SELECT id, data FROM releases"):
            return _FakeCursor(sorted(self.releases.items()))
        if sql.startswith("SELECT id, data FROM albums"):
            return _FakeCursor(sorted(self.albums.items()))
        if sql.startswith("INSERT INTO albums"):
            self.albums[params[0]] = params[1]
        if sql.startswith("INSERT INTO tracks"):
            self.tracks[params[0]] = params[1]
        return _FakeCursor([])

    def commit(self):
        self.committed = True


def test_publish_allocates_past_the_legacy_catalogue_and_is_idempotent(tmp_path: Path):
    conductor = _conductor(tmp_path)
    booking = _booking(conductor, minutes=110.0)
    conductor.run_one_album(booking)
    run_dir = tmp_path / booking.run_id

    legacy = {f"{i:04d}": {"title": f"legacy {i}"} for i in range(1, 8)}
    conn = _FakeConn(legacy)
    first = publish_album(run_dir, connection=conn)
    assert first.release_id == "0008"  # AFAR-0008 follows AFAR-0007
    assert first.artist_id == booking.artist_id
    assert conn.committed and len(conn.tracks) == booking.size.tracks
    # The legacy releases table is untouched — nothing renamed, nothing rewritten.
    assert conn.releases == legacy

    # The second hop (once the staff have reacted) keeps the same number.
    second = publish_album(run_dir, connection=conn)
    assert second.release_id == "0008" and len(conn.albums) == 1


def test_publish_dry_writes_nothing_and_still_computes_everything(tmp_path: Path):
    conductor = _conductor(tmp_path)
    booking = _booking(conductor, minutes=110.0)
    conductor.run_one_album(booking)
    outcome = publish_album(tmp_path / booking.run_id, dry_run=True)
    assert outcome.dry_run is True and outcome.release_id == "0000"
    assert outcome.tracks == booking.size.tracks
    assert outcome.media_bytes > 1000 * booking.size.tracks
    assert outcome.reacted is True  # the reactions are already logged
