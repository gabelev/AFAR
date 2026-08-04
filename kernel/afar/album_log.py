"""Reading the album log back: what has been recorded, and what an artist hears.

Architecture rule 3 — the JSONL log under `runs/` is authoritative — has a
practical consequence for the loop: the conductor must not REMEMBER anything.
Who recorded last, what the town has released, which records reached whose
ears and at what coordinates the audio was logged: all of it is read back out
of the log on every booking, so a fresh process on a fresh machine books and
hears exactly what the last one would have.

Three reads, in order of how much they touch:

- `album_rows` / `recorded_history` — the `albums.jsonl` rows across every
  run, oldest first, and the artist ids in that order (the rotation's input).
- `heard_for` — the sleeves an artist about to record gets to hear: the most
  recent albums by OTHER artists, one per artist so a prolific act cannot
  crowd the room, plus that artist's own last record. Every one of them goes
  through `heard_album_from_row`, the whitelist adapter, so a logged row's
  staff blocks are structurally unable to reach an artist.
- `build_ears` — the runner-side measurements (`Ears`): audio files and logged
  embeddings keyed by artifact hash, the recording artist's own album-level
  history, and each heard artist's previous album position. Numbers and paths,
  never words — this never enters a prompt except as the ear's measured facts.

Nothing here writes. Nothing here decides.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from afar import features
from afar.perception.album_context import Ears, HeardAlbum, heard_album_from_row

#: How many other artists' records reach one artist before it writes. Enough
#: that the town is audible, few enough that the sleeve text stays readable
#: inside one prompt.
HEARD_LIMIT = 4


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_dirs(runs_root: Path) -> list[Path]:
    root = Path(runs_root)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name != "audio")


def album_rows(runs_root: Path) -> list[dict[str, Any]]:
    """Every logged album row across ALL runs, oldest first by timestamp.

    One row per finished record (`afar.run.run_album` writes it), carrying the
    album's content hash as `id` and the whole album record under `record`.
    """
    rows: list[dict[str, Any]] = []
    for run_dir in _run_dirs(runs_root):
        rows.extend(_read_jsonl(run_dir / "albums.jsonl"))
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def recorded_history(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The artist ids of every recorded album, oldest first — the rotation's
    whole memory (`afar.booking.rotation_order`)."""
    history: list[str] = []
    for row in rows:
        artist_id = str(row.get("player") or _record(row).get("artist_id") or "")
        if artist_id:
            history.append(artist_id)
    return history


def _record(row: Mapping[str, Any]) -> Mapping[str, Any]:
    record = row.get("record")
    return record if isinstance(record, Mapping) else {}


def _sleeve_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """One logged album row flattened to the shape `heard_album_from_row`
    reads: the sleeve, plus each track's ARTIFACT hash.

    The album body (`record.album`) carries the words; the rendered list
    (`record.tracks`) carries the hashes, and the ear needs the hashes to join
    a sleeve line to the audio it describes. Track order is the album's own,
    so index is a safe join.
    """
    record = _record(row)
    body = record.get("album") if isinstance(record.get("album"), Mapping) else {}
    rendered = record.get("tracks") if isinstance(record.get("tracks"), Sequence) else ()
    hashes = [
        str(t.get("hash", "")) for t in rendered if isinstance(t, Mapping)
    ]
    tracks = []
    for i, track in enumerate(body.get("tracks") or ()):
        if not isinstance(track, Mapping):
            continue
        tracks.append(
            {
                "title": track.get("title", ""),
                "note": track.get("note", ""),
                "hash": hashes[i] if i < len(hashes) else "",
            }
        )
    return {
        "artist_id": body.get("artist_id") or record.get("artist_id") or row.get("player") or "",
        "title": body.get("title", ""),
        "description": body.get("description", ""),
        "tracks": tracks,
        "album_id": str(record.get("album_id") or row.get("id") or ""),
    }


def heard_for(
    rows: Sequence[Mapping[str, Any]],
    artist_id: str,
    *,
    names: Mapping[str, str] = {},
    limit: int = HEARD_LIMIT,
) -> tuple[tuple[HeardAlbum, ...], Optional[HeardAlbum]]:
    """What `artist_id` hears before it writes: (other artists' records, own last).

    The most recent record by each of the last `limit` OTHER artists to
    release — one per artist, newest first, so a prolific act cannot fill the
    room with its own back catalogue. Everything crosses through
    `heard_album_from_row`: six whitelisted sleeve fields, never a staff word.
    """
    others: list[HeardAlbum] = []
    seen: set[str] = set()
    own_last: Optional[HeardAlbum] = None
    for row in reversed(list(rows)):
        sleeve = _sleeve_row(row)
        maker = str(sleeve["artist_id"])
        if not maker:
            continue
        if maker == artist_id:
            if own_last is None:
                own_last = heard_album_from_row(
                    sleeve, artist_name=names.get(maker, maker), album_id=sleeve["album_id"]
                )
            continue
        if maker in seen or len(others) >= limit:
            continue
        seen.add(maker)
        others.append(
            heard_album_from_row(
                sleeve, artist_name=names.get(maker, maker), album_id=sleeve["album_id"]
            )
        )
    others.reverse()  # oldest of the heard set first — the order they landed
    return tuple(others), own_last


# --- the instruments' side: what was measured, not what was said --------------


def _artifact_index(runs_root: Path) -> dict[tuple[str, int], tuple[str, Path]]:
    """(album_id, track index) -> (artifact hash, audio path), across all runs."""
    index: dict[tuple[str, int], tuple[str, Path]] = {}
    for run_dir in _run_dirs(runs_root):
        for row in _read_jsonl(run_dir / "artifacts.jsonl"):
            album_id = str(row.get("album", ""))
            if not album_id or "track" not in row:
                continue
            path = Path(str(row.get("path", "")))
            if not path.is_file():
                fallback = Path(runs_root) / "audio" / path.name
                path = fallback if fallback.is_file() else path
            index[(album_id, int(row["track"]))] = (str(row.get("hash", "")), path)
    return index


def _embedding_index(runs_root: Path) -> dict[str, dict[tuple[str, int], list[float]]]:
    """space -> (album_id, track index) -> the vector that track was logged at.

    Keyed on (album, track) rather than the row's own id because the two spaces
    key differently (`artifact_id` vs `intent_id`) and the ear joins on the
    artifact hash for both — the same coordinates the features were computed
    from, so what an artist is told and what `features.py` claims cannot drift.
    """
    index: dict[str, dict[tuple[str, int], list[float]]] = {}
    for run_dir in _run_dirs(runs_root):
        for row in _read_jsonl(run_dir / "embeddings.jsonl"):
            album_id = str(row.get("album", ""))
            space = str(row.get("space", ""))
            if not album_id or not space or "track" not in row:
                continue
            vector = row.get("vector")
            if not isinstance(vector, Sequence):
                continue
            index.setdefault(space, {})[(album_id, int(row["track"]))] = [
                float(v) for v in vector
            ]
    return index


def build_ears(
    runs_root: Path,
    rows: Sequence[Mapping[str, Any]],
    artist_id: str,
    heard: Sequence[HeardAlbum],
) -> Ears:
    """The runner-side measurement material for one booking.

    - `audio` / `vectors`: every heard track's file and logged embedding,
      keyed by artifact hash (what `measure_heard_albums` and `_album_features`
      join on).
    - `own_past`: the recording artist's own previous albums as album-level
      vectors, oldest first — novelty's history, and what "did they move
      toward you" is measured against.
    - `maker_past`: each OTHER artist's previous album position, i.e. the one
      before the record being heard, so "toward you or away" compares like
      with like.
    """
    artifacts = _artifact_index(runs_root)
    embeddings = _embedding_index(runs_root)
    spaces = tuple(embeddings) or ("audio", "intent")

    wanted = {a.album_id for a in heard if a.album_id}
    audio: dict[str, Path] = {}
    vectors: dict[str, dict[str, list[float]]] = {space: {} for space in spaces}
    for (album_id, track), (digest, path) in artifacts.items():
        if album_id not in wanted or not digest:
            continue
        if path.is_file():
            audio[digest] = path
        for space in spaces:
            vector = embeddings.get(space, {}).get((album_id, track))
            if vector is not None:
                vectors[space][digest] = vector

    # Album-level positions, per artist, in log order.
    by_artist: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        record = _record(row)
        album_id = str(record.get("album_id") or row.get("id") or "")
        maker = str(row.get("player") or record.get("artist_id") or "")
        if album_id and maker:
            by_artist.setdefault(maker, []).append((album_id, maker))

    def _album_vec(album_id: str, space: str) -> Optional[list[float]]:
        track_vecs = [
            vector
            for (a_id, _track), vector in sorted(embeddings.get(space, {}).items())
            if a_id == album_id
        ]
        return features.album_vector(track_vecs) if track_vecs else None

    own_past: dict[str, list[list[float]]] = {}
    for space in spaces:
        history = []
        for album_id, _ in by_artist.get(artist_id, ()):
            vector = _album_vec(album_id, space)
            if vector is not None:
                history.append(vector)
        if history:
            own_past[space] = history

    heard_ids = {a.artist_id: a.album_id for a in heard}
    maker_past: dict[str, dict[str, list[float]]] = {}
    for space in spaces:
        previous: dict[str, list[float]] = {}
        for maker, albums in by_artist.items():
            if maker not in heard_ids:
                continue
            ids = [album_id for album_id, _ in albums]
            heard_id = heard_ids[maker]
            before = ids[: ids.index(heard_id)] if heard_id in ids else ids
            for album_id in reversed(before):
                vector = _album_vec(album_id, space)
                if vector is not None:
                    previous[maker] = vector
                    break
        if previous:
            maker_past[space] = previous

    return Ears(audio=audio, vectors=vectors, own_past=own_past, maker_past=maker_past)
