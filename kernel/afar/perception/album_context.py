"""build_album_context: the ONE place an artist's ears are wired.

Architecture rule 1 / docs/SPEC.md ("the law: staff never touch the artifact").
What an artist may hear before it writes a record is decided here and nowhere
else, and the enforcement is STRUCTURAL rather than by convention:

- this function's signature has no staff channel at all — no `direction`, no
  brief, no review, no reaction, no verdict parameter exists to pass one
  through, so a staff voice in an artist's prompt would have to be a bug in
  this one file;
- this module imports nothing staff-shaped (`afar.staff`, the staff agents),
  and a test pins that;
- every dict that leaves here is assembled key by key from a whitelist
  (`HeardAlbum.to_context` / `HeardTrack.to_context`), so handing this module
  a whole logged release row — staff blocks and all — cannot leak the
  commentary into the artist's prompt. `heard_album_from_row` is the adapter
  for exactly that case.

What DOES cross, per the spec's hearing section: other artists' recent albums
as SLEEVE TEXT (title, description, track titles, the artist's own note per
track) plus, for tracks actually heard, the measured facts of what the audio
sounded like from this listener's seat (`afar.perception.ear`) — and the
artist's own last record.

The returned dict is double-duty, exactly like `build_context`'s: it is the
input to `Player.write_album` AND the `context` field of the logged
perceptions row, so the log records what the artist actually saw. It must
stay JSON-serializable.

The isolation control (`isolated=True`, the experiment's third condition
behind `AFAR_EXPERIMENT_MODE`) hears no other artist at all — `heard` is
present and empty so the logged row makes the absence explicit — while an
artist's own last record stays, because remembering your own work is not
hearing someone else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from afar.perception.ear import HEARD_KEYS

#: Every key one heard TRACK may carry into a context. A whitelist, not a
#: blacklist: a field nobody named here cannot cross, whatever a caller packs
#: into the row it built its HeardTrack from.
TRACK_KEYS: tuple[str, ...] = ("title", "note", "content_hash", "heard")

#: Every key one heard ALBUM may carry into a context. Sleeve text only —
#: there is deliberately no slot for a review, a verdict, a brief or a
#: reaction, and no slot for the maker's private rationale.
ALBUM_KEYS: tuple[str, ...] = (
    "artist_id",
    "artist_name",
    "album_id",
    "title",
    "description",
    "tracks",
)


@dataclass(frozen=True)
class HeardTrack:
    """One song on a record someone else made, as this artist receives it.

    Sleeve text (`title`, `note` — the one line its maker said about it) plus
    `heard`: the MEASURED facts of what the audio sounded like from this
    listener's seat, or None for a track this artist never actually heard
    (no audio, no embedding — the honest answer is silence, not a guess).
    `content_hash` is the artifact id: the join key back to the audio file and
    its logged embedding, and what the ear measurement is keyed on.
    """

    title: str
    note: str = ""
    content_hash: str = ""
    heard: Optional[Mapping[str, Any]] = None

    def to_context(self) -> dict[str, Any]:
        item: dict[str, Any] = {"title": str(self.title), "note": str(self.note)}
        if self.content_hash:
            item["content_hash"] = str(self.content_hash)
        if self.heard:
            # Only the ear's own keys — the heard dict is measurement, and a
            # caller cannot smuggle prose in beside it.
            item["heard"] = {k: self.heard[k] for k in HEARD_KEYS if k in self.heard}
        return item


@dataclass(frozen=True)
class HeardAlbum:
    """One finished record, as another artist receives it: the sleeve.

    Title, description, and the songs — nothing about how the record was
    received, because reception is the staff's half of the world and it never
    crosses back.
    """

    artist_id: str
    title: str
    description: str
    tracks: tuple[HeardTrack, ...] = ()
    #: How the room says this artist's name (display or first name). Falls back
    #: to the id, which is at least true.
    artist_name: str = ""
    #: Catalogue id or content hash — the album's identity in the log.
    album_id: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "artist_id": str(self.artist_id),
            "artist_name": str(self.artist_name or self.artist_id),
            "album_id": str(self.album_id),
            "title": str(self.title),
            "description": str(self.description),
            "tracks": [t.to_context() for t in self.tracks],
        }

    def with_heard(self, heard_by_hash: Mapping[str, Mapping[str, Any]]) -> "HeardAlbum":
        """This album with measured ear facts attached to the tracks that have
        them (keyed by artifact hash). Tracks with no measurement are left
        exactly as they were."""
        return HeardAlbum(
            artist_id=self.artist_id,
            title=self.title,
            description=self.description,
            tracks=tuple(
                HeardTrack(
                    title=t.title,
                    note=t.note,
                    content_hash=t.content_hash,
                    heard=heard_by_hash.get(t.content_hash, t.heard),
                )
                for t in self.tracks
            ),
            artist_name=self.artist_name,
            album_id=self.album_id,
        )


def heard_album_from_row(
    row: Mapping[str, Any], *, artist_name: str = "", album_id: str = ""
) -> HeardAlbum:
    """A logged album row -> a HeardAlbum, through the whitelist.

    THE adapter the conductor uses, and the reason the no-staff law survives
    contact with reality: a logged release row carries the staff's blocks
    (reviews, briefs, reactions, liner notes) right beside the sleeve, and
    this function reads exactly six fields out of it. Anything else in the row
    — now or in a future schema — is structurally unable to reach an artist.

    Accepts either the `Album.to_row()` shape or a row that nests it under
    "album"/"record".
    """
    body = row
    for key in ("album", "record"):
        nested = row.get(key)
        if isinstance(nested, Mapping) and "tracks" in nested:
            body = nested
            break
    raw_tracks = body.get("tracks")
    tracks: list[HeardTrack] = []
    if isinstance(raw_tracks, Sequence) and not isinstance(raw_tracks, (str, bytes)):
        for raw in raw_tracks:
            if not isinstance(raw, Mapping):
                continue
            tracks.append(
                HeardTrack(
                    title=str(raw.get("title", "")),
                    note=str(raw.get("note", "")),
                    content_hash=str(raw.get("content_hash", "") or raw.get("hash", "")),
                )
            )
    return HeardAlbum(
        artist_id=str(body.get("artist_id", "")),
        title=str(body.get("title", "")),
        description=str(body.get("description", "")),
        tracks=tuple(tracks),
        artist_name=str(artist_name or body.get("artist_name", "")),
        album_id=str(album_id or body.get("album_id", "") or body.get("content_hash", "")),
    )


@dataclass(frozen=True)
class Ears:
    """What the RUNNER measured about the records an artist heard.

    Numbers and file paths, never words: this is the raw material the ear pass
    and the album-cadence features are computed from, and it deliberately does
    NOT enter the context — the context is what the artist reads, the ears are
    what the instruments recorded. Everything is keyed by artifact hash (the
    content-addressed track id) so it joins the log without a second index.

    - `audio`: artifact hash -> the file on disk, for DSP.
    - `vectors`: space ("audio" | "intent") -> artifact hash -> that track's
      logged embedding.
    - `own_past`: space -> this artist's own PREVIOUS albums as album-level
      vectors, oldest first (novelty's history; the last one is what the ear's
      relations compare against).
    - `maker_past`: space -> other artist id -> that artist's previous
      album-level vector, for "did they move toward you or away".
    """

    audio: Mapping[str, Path] = field(default_factory=dict)
    vectors: Mapping[str, Mapping[str, Sequence[float]]] = field(default_factory=dict)
    own_past: Mapping[str, Sequence[Sequence[float]]] = field(default_factory=dict)
    maker_past: Mapping[str, Mapping[str, Sequence[float]]] = field(default_factory=dict)

    def space(self, space: str) -> Mapping[str, Sequence[float]]:
        return self.vectors.get(space, {})

    def own_last(self, space: str) -> Optional[Sequence[float]]:
        past = self.own_past.get(space) or ()
        return past[-1] if past else None

    def own_before_last(self, space: str) -> Optional[Sequence[float]]:
        past = self.own_past.get(space) or ()
        return past[-2] if len(past) >= 2 else None


def build_album_context(
    artist_id: str,
    *,
    heard: Sequence[HeardAlbum] = (),
    own_last: Optional[HeardAlbum] = None,
    isolated: bool = False,
) -> dict[str, Any]:
    """Build everything `artist_id` has heard, as the artist will read it.

    THE chokepoint. Returns a JSON-serializable dict that is both the input to
    `Player.write_album` and the logged perceptions row's `context`.

    There is no staff parameter, and there never may be one: if the Producer,
    Critic, Muse, Listener or Archivist ever needs to reach an artist, the
    answer is no. That is the whole law, and this signature is where it lives.

    `heard` is other artists' recent records; `own_last` is this artist's own
    previous one. `isolated=True` is the experiment's isolation control: no
    other artist is heard at all (`heard` stays present and empty so the log
    says so plainly), while the artist's own last record remains.
    """
    if not artist_id:
        raise ValueError("build_album_context needs an artist_id")
    others = [
        album.to_context() for album in heard if album.artist_id != artist_id
    ]
    context: dict[str, Any] = {
        "artist_id": artist_id,
        "isolated": bool(isolated),
        "heard": [] if isolated else others,
    }
    if own_last is not None:
        context["own_last"] = own_last.to_context()
    return context
