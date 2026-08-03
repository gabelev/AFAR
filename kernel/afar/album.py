"""Album: a whole record, written by one artist in one breath.

The album is AFAR's unit of work (docs/SPEC.md). An artist writes the title,
the description and every song — words and DNA — in a single call, before any
audio exists. Songs are written to the album; the album is never a caption
applied to finished songs afterwards, and no staff voice names any of it.

Each track carries its own `Intent` because the renderer's only input is DNA:
the album is the creative act, the per-track Intent is the contract with the
renderer, and both are logged. A track's Intent keeps the artist's `player_id`
and its `lyrics`; its `line` carries what the artist says about that song.

Parsing is deliberately tolerant of the shapes models actually emit (fences,
prose wrappers, a `tracks` list of objects) and strict about semantics: a bad
album raises ValueError and the caller decides whether to re-prompt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from afar.intent import Intent, _loads_lenient

#: A record has to be a record: fewer is a single, more is an anthology no
#: budget survives. The conductor picks the exact count inside this range.
MIN_TRACKS = 2
MAX_TRACKS = 6


@dataclass(frozen=True)
class AlbumTrack:
    """One song: what it is called, what it says, and the DNA that renders it."""

    title: str
    intent: Intent
    #: One line from the artist about this song — the world's speech bubble.
    note: str = ""

    @property
    def lyrics(self) -> str:
        """The sung words. They live on the Intent — the renderer's only input."""
        return self.intent.lyrics

    def to_row(self) -> dict[str, Any]:
        """The logged shape: title + note + the full DNA dict."""
        return {
            "title": self.title,
            "note": self.note,
            "lyrics": self.intent.lyrics,
            "intent": self.intent.to_dna_dict(),
        }


@dataclass(frozen=True)
class Album:
    """A finished record as the artist conceived it, before a note exists."""

    artist_id: str
    title: str
    #: 1-2 sentences on the record as a body of work, in the artist's voice.
    description: str
    tracks: tuple[AlbumTrack, ...]
    #: The artist's own framing of why this record, now — logged, never rendered.
    rationale: str = ""

    def validate(self) -> "Album":
        if not self.artist_id:
            raise ValueError("album artist_id must not be empty")
        if not self.title.strip():
            raise ValueError("album title must not be empty")
        if not self.description.strip():
            raise ValueError("album description must not be empty")
        if not MIN_TRACKS <= len(self.tracks) <= MAX_TRACKS:
            raise ValueError(
                f"album must carry {MIN_TRACKS}-{MAX_TRACKS} tracks, got {len(self.tracks)}"
            )
        titles = [t.title.strip().lower() for t in self.tracks]
        if any(not t for t in titles):
            raise ValueError("every track needs a title")
        if len(set(titles)) != len(titles):
            raise ValueError("track titles must differ from each other")
        if self.title.strip().lower() in titles:
            raise ValueError("the album title must differ from every track title")
        for track in self.tracks:
            if track.intent.player_id != self.artist_id:
                raise ValueError(
                    f"track {track.title!r} carries player_id "
                    f"{track.intent.player_id!r}, not the album's {self.artist_id!r}"
                )
        return self

    def content_hash(self) -> str:
        """Stable hash of everything the artist decided — the album's identity."""
        payload = {
            "artist_id": self.artist_id,
            "title": self.title,
            "description": self.description,
            "tracks": [
                {"title": t.title, "note": t.note, "intent": t.intent.content_hash()}
                for t in self.tracks
            ],
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_row(self) -> dict[str, Any]:
        """The logged shape of a whole album."""
        return {
            "artist_id": self.artist_id,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "content_hash": self.content_hash(),
            "tracks": [t.to_row() for t in self.tracks],
        }

    @classmethod
    def from_json(cls, text: str, *, artist_id: str) -> "Album":
        """Parse a model reply into an Album, or raise ValueError.

        `artist_id` is supplied by the caller rather than trusted from the
        reply: who is recording is a fact of the session, not a thing the
        model gets to assert. Each track's Intent is stamped with it, so a
        model that omits or misspells `player_id` still yields a valid album.
        """
        data = _loads_lenient(text)
        if not isinstance(data, Mapping):
            raise ValueError("album JSON must be an object")
        raw_tracks = data.get("tracks")
        if not isinstance(raw_tracks, Sequence) or isinstance(raw_tracks, (str, bytes)):
            raise ValueError("album JSON needs a `tracks` list")
        tracks: list[AlbumTrack] = []
        for i, raw in enumerate(raw_tracks):
            if not isinstance(raw, Mapping):
                raise ValueError(f"track {i} is not an object")
            intent_blob = raw.get("intent")
            if not isinstance(intent_blob, Mapping):
                raise ValueError(f"track {i} is missing its `intent` object")
            payload = dict(intent_blob)
            payload["player_id"] = artist_id
            # The note is what the artist says about this song — one source,
            # so the log, the sleeve and the world's speech bubble agree. It
            # wins over any `line` in the DNA; absent, the DNA's line is it.
            note = str(raw.get("note", "")).strip()
            if note:
                payload["line"] = note
            else:
                note = str(payload.get("line", "")).strip()
            try:
                intent = Intent.from_json(json.dumps(payload))
            except ValueError as err:
                raise ValueError(f"track {i} ({raw.get('title')!r}): {err}") from err
            tracks.append(
                AlbumTrack(
                    title=str(raw.get("title", "")).strip(),
                    intent=intent,
                    note=note,
                )
            )
        try:
            album = cls(
                artist_id=artist_id,
                title=str(data["title"]).strip(),
                description=str(data["description"]).strip(),
                tracks=tuple(tracks),
                rationale=str(data.get("rationale", "")).strip(),
            )
        except KeyError as err:
            raise ValueError(f"album JSON is missing {err}") from err
        return album.validate()
