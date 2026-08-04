"""The staff react — after the record exists, and never to anyone but the public.

Architecture rule 1 (docs/SPEC.md): the Producer, Critic, Muse, Listener and
Archivist read FINISHED albums and react in public. Nothing any of them
writes reaches an artist before or during the writing of a record: no session
direction, no cut, no veto, no staff-written title. This module is that law
in code — `run_reactions` takes a PUBLISHED `Album`, walks the five reactions
in order, appends each as a `staff` row, and returns what they said.

Three structural facts make the law hard to break here:

1. `run_reactions` runs only on a published album — it refuses without the
   release id of the record it is reacting to. There is no path that reaches
   a staff member before publication.
2. It writes LOG ROWS ONLY. It never rewrites the album, its record, or its
   tracks; a reaction cannot alter the thing it reacts to even by accident.
3. Nothing it returns is handed to an artist. The artist's context is built
   by one function (afar.perception) with no staff channel at all.

Order is by convention, not dependence: Producer (the room's reaction),
Critic (the public verdict), Muse (what the scene is doing), Listener (the
fan), Archivist (the shelf and the liner notes). The Listener reads the
Critic's verdict the way any fan reads a review — staff prose reaching staff
prose is public commentary, not influence.

THE DEGRADATION DOCTRINE (DECISIONS.md: the material always outranks the
commentary): every stage is wrapped individually. A stage that still fails
after the retry ladder (afar.agents.robust) logs a `staff_stage_failed` row
and the chain CONTINUES with that reaction absent. A failed reaction never
blocks, delays or alters a release — the record is already out.

The ROUND-BASED instrument (`run_staff` and everything it walks: the panel,
the cut, the veto, the naming call, the brief) lives in `afar.staff_rounds`
and is reachable from here only through the compatibility `__getattr__` at
the bottom of this module. It never touches an album.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from afar.album import Album
from afar.config import AfarConfig
from afar.log import JsonlLedger, RunContext

#: Display-only stage names (DECISIONS.md): staff prose uses these; ids never change.
STAGE_NAMES: dict[str, str] = {"silt": "Delta Marlowe", "rust": "Roan Patina", "keep": "Evers Lane"}

#: Staff surnames — the register the Critic writes in (DECISIONS.md naming rule).
SURNAMES: dict[str, str] = {"silt": "Marlowe", "rust": "Patina", "keep": "Lane"}

#: The table every album reaction lands in, one row per stage.
STAFF_TABLE = "staff"

#: The reactions, in the order they are run and published.
REACTION_STAGES: tuple[str, ...] = ("producer", "critic", "muse", "listener", "archivist")

#: The honest public sentence each degraded reaction leaves behind. None of
#: them apologises for the record: the record shipped either way.
REACTION_DEGRADED_NOTES: dict[str, str] = {
    "producer": "The Producer did not react to this record.",
    "critic": "The Critic did not file on this record.",
    "muse": "The Muse did not file this time — no note on the scene alongside this record.",
    "listener": "The Listener did not file this time.",
    "archivist": (
        "The Archivist did not file this time — the record stands unshelved; "
        "the songs speak for themselves."
    ),
}


# --- shared log helpers (the round-based instrument imports these too) --------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def newest_release_path(run_dir: Path) -> Path:
    """The run's most recent release-*.json by mtime — the record to build on."""
    candidates = sorted(
        run_dir.glob("release-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        raise FileNotFoundError(f"no release-*.json under {run_dir}")
    return candidates[0]


def _short_error(err: BaseException) -> str:
    return f"{type(err).__name__}: {err}"[:300]


def _load_recent_rows(
    runs_root: Path, table: str, kind: str, *, exclude_run: str | None = None
) -> list[dict[str, Any]]:
    """All rows of one kind from one table across ALL runs, oldest first.
    Reading the log, not remembering, is the point (rule 3): a fresh process
    on a fresh machine sees the same shelf."""
    runs_root = Path(runs_root)
    rows: list[dict[str, Any]] = []
    if runs_root.exists():
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            if run_dir.name == exclude_run:
                continue
            path = run_dir / f"{table}.jsonl"
            if path.exists():
                rows.extend(r for r in _read_jsonl(path) if r.get("kind") == kind)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def load_recent_reactions(
    runs_root: Path, *, exclude_run: str | None = None, limit: int = 6
) -> list[dict[str, Any]]:
    """The Listener's most recent logged reactions across ALL runs — the fan's
    word as the Muse reads it. Reading the log, not remembering, is the point:
    a fresh process on a fresh machine hears the same fan.

    Both homes are read: `staff.jsonl` (album reactions, this module) and
    `reactions.jsonl` (the round-based instrument's rows), merged oldest
    first. The log is append-only, so old rows keep their old shape forever.
    """
    rows = [
        *_load_recent_rows(runs_root, STAFF_TABLE, "listener_reaction", exclude_run=exclude_run),
        *_load_recent_rows(runs_root, "reactions", "reaction", exclude_run=exclude_run),
    ]
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows[-limit:]


def artist_display_name(artist_id: str) -> str:
    """The name the staff say out loud. The house trio's stage names, then the
    committed roster's display name, then the id — never a lookup failure."""
    if artist_id in STAGE_NAMES:
        return STAGE_NAMES[artist_id]
    entry = Path(__file__).resolve().parent / "agents" / "roster" / f"{artist_id}.json"
    if entry.exists():
        try:
            return str(json.loads(entry.read_text(encoding="utf-8"))["display_name"])
        except (ValueError, KeyError):
            pass
    return artist_id


def album_digest(album: Album, *, artist_name: str = "") -> dict[str, Any]:
    """One finished record as the staff read it: the sleeve and the words.

    Deliberately the SLEEVE ONLY — title, description, and each song's title,
    the artist's line about it, and what is sung. No DNA dials, no palette
    numbers, no rendering plan: staff prose is public (the plain-language
    house law), and a digest that never carries a dial name cannot leak one.
    """
    return {
        "artist": artist_name or artist_display_name(album.artist_id),
        "album": album.title,
        "the_artist_on_the_record": album.description,
        "songs": [
            {"title": t.title, "the_artist_on_this_song": t.note, "sung": t.lyrics}
            for t in album.tracks
        ],
    }


def tracks_line(album: Album) -> str:
    """The machine-readable roll call every per-track reply is checked against."""
    return "TRACKS: " + ", ".join(t.title for t in album.tracks)


# --- what one pass of reactions produced --------------------------------------


@dataclass(frozen=True)
class AlbumReactions:
    """What the staff said about one published album. Any piece may be None
    when its stage degraded (named in `degraded`) — the album is unaffected
    either way; it was already out when the first reaction was written."""

    album_id: str  # the album's content hash — what was reacted to
    release_id: str  # the published record the reactions hang off
    artist_id: str
    producer: Optional[Any] = None  # afar.agents.producer.AlbumReaction
    review: Optional[Any] = None  # afar.agents.critic.AlbumReview
    scene_note: Optional[Any] = None  # afar.agents.muse.SceneNote
    listener: Optional[Any] = None  # afar.agents.listener.Reaction
    shelving: Optional[Any] = None  # afar.agents.archivist.AlbumShelving
    degraded: tuple[str, ...] = ()

    def to_row(self) -> dict[str, Any]:
        """The whole pass as one dict — what a publisher hangs off a release."""
        row: dict[str, Any] = {}
        if self.producer is not None:
            row["producer"] = {
                "text": self.producer.text,
                "who_for": self.producer.who_for,
                "what_it_does": self.producer.what_it_does,
            }
        if self.review is not None:
            row["critic"] = {
                "verdict": self.review.verdict,
                "track_notes": dict(self.review.track_notes),
            }
        if self.scene_note is not None:
            row["muse"] = {
                "theme": self.scene_note.theme,
                "text": self.scene_note.body,
                "sources": list(self.scene_note.sources),
                "thin": self.scene_note.thin,
                "stance": self.scene_note.stance,
            }
        if self.listener is not None:
            row["listener"] = {
                "valence": self.listener.valence,
                "text": self.listener.text,
                "disagreements_with_critic": list(self.listener.disagreements_with_critic),
            }
        if self.shelving is not None:
            row["archivist"] = {
                "placement": self.shelving.placement,
                "arc": self.shelving.arc,
                "liner_notes": self.shelving.notes,
                "callouts": [dict(c) for c in self.shelving.callouts],
            }
        if self.degraded:
            row["degraded"] = {
                stage: REACTION_DEGRADED_NOTES[stage] for stage in self.degraded
            }
        return row


# --- the frame: five reactions to a record that is already out ----------------


def run_reactions(
    album: Album,
    *,
    run_dir: Path,
    config: AfarConfig,
    release_id: str,
    artist_name: str = "",
    stance: str = "",
    perceiver: Any = None,
    heard: Sequence[Mapping[str, Any]] = (),
) -> AlbumReactions:
    """Walk the staff over one PUBLISHED album and log what they said.

    `release_id` is the id of the published record — required, and the whole
    guard: the staff react to records that exist, so a caller that has not
    published yet cannot reach a staff member at all (ValueError). `heard` is
    what the artist heard before writing, as the publisher logged it — read by
    the Critic as context for the verdict, never sent anywhere near an artist.

    Appends one `staff` row per reaction (kinds: producer_reaction,
    album_review, scene_note, listener_reaction, shelving) plus a
    `staff_stage_failed` row for any stage that degraded. It writes NOTHING
    else: no release record is rewritten, no track is renamed, no album field
    is touched. The reactions are commentary hung off a finished record.
    """
    from afar.agents.archivist import ArchivistAgent
    from afar.agents.critic import CriticAgent
    from afar.agents.listener import ListenerAgent
    from afar.agents.muse import MuseAgent
    from afar.agents.producer import ProducerAgent

    if not str(release_id).strip():
        raise ValueError(
            "run_reactions needs the release id of a PUBLISHED album — the staff "
            "react to a record that exists; nothing here runs before publication"
        )
    album.validate()
    run_dir = Path(run_dir)
    artist_name = artist_name or artist_display_name(album.artist_id)
    album_id = album.content_hash()
    ledger = JsonlLedger(
        run_dir.parent, run_dir.name, context=RunContext(code_sha=config.code_sha)
    )
    stamps = {
        "album_id": album_id,
        "release_id": str(release_id),
        "artist": album.artist_id,
    }
    degraded: list[str] = []

    def _failed(stage: str, err: BaseException) -> None:
        degraded.append(stage)
        ledger.write(
            STAFF_TABLE,
            {
                **stamps,
                "kind": "staff_stage_failed",
                "agent": stage,
                "stage": stage,
                "error": _short_error(err),
                "note": REACTION_DEGRADED_NOTES[stage],
            },
        )

    # --- the Producer: the room's reaction. It books nothing. -----------------
    producer_reaction: Any = None
    try:
        producer_reaction = ProducerAgent(config.model).react_to_album(
            album, artist_name=artist_name
        )
    except Exception as err:  # noqa: BLE001 — the material outranks the commentary
        _failed("producer", err)
    else:
        ledger.write(
            STAFF_TABLE,
            {
                **stamps,
                "kind": "producer_reaction",
                "agent": "producer",
                "text": producer_reaction.text,
                "who_for": producer_reaction.who_for,
                "what_it_does": producer_reaction.what_it_does,
            },
        )

    # --- the Critic: the public verdict. It names nothing. --------------------
    review: Any = None
    try:
        review = CriticAgent(config.model).review_album(
            album, artist_name=artist_name, heard=heard
        )
    except Exception as err:  # noqa: BLE001 — same doctrine, independent stage
        _failed("critic", err)
    else:
        ledger.write(
            STAFF_TABLE,
            {
                **stamps,
                "kind": "album_review",
                "agent": "critic",
                "text": review.verdict,
                "track_notes": dict(review.track_notes),
            },
        )

    # --- the Muse: what the scene is doing. It briefs no one. -----------------
    scene_note: Any = None
    try:
        from afar.perception.field import ProvenanceLog, build_perceiver

        muse = MuseAgent(
            config.model,
            perceiver=(
                perceiver
                if perceiver is not None
                else build_perceiver(config.live, config.model, ProvenanceLog())
            ),
        )
        scene_note = muse.read_scene(
            albums=[album],
            reaction_rows=load_recent_reactions(run_dir.parent, exclude_run=run_dir.name),
            stance=stance,
            artist_names={album.artist_id: artist_name},
        )
    except Exception as err:  # noqa: BLE001
        _failed("muse", err)
    else:
        ledger.write(
            STAFF_TABLE,
            {
                **stamps,
                "kind": "scene_note",
                "agent": "muse",
                "theme": scene_note.theme,
                "text": scene_note.body,
                "sources": list(scene_note.sources),
                "thin": scene_note.thin,
                "stance": scene_note.stance,
            },
        )

    # --- the Listener: did I like it -----------------------------------------
    reaction: Any = None
    try:
        reaction = ListenerAgent(config.model).react_to_album(
            album,
            artist_name=artist_name,
            critic_verdict=review.verdict if review is not None else "",
        )
    except Exception as err:  # noqa: BLE001
        _failed("listener", err)
    else:
        ledger.write(
            STAFF_TABLE,
            {
                **stamps,
                "kind": "listener_reaction",
                "agent": "listener",
                "valence": reaction.valence,
                "text": reaction.text,
                "disagreements_with_critic": list(reaction.disagreements_with_critic),
            },
        )

    # --- the Archivist, last: the shelf and the liner notes -------------------
    shelving: Any = None
    try:
        shelving = ArchivistAgent(config.model).shelve_album(album, artist_name=artist_name)
    except Exception as err:  # noqa: BLE001
        _failed("archivist", err)
    else:
        ledger.write(
            STAFF_TABLE,
            {
                **stamps,
                "kind": "shelving",
                "agent": "archivist",
                "placement": shelving.placement,
                "arc": shelving.arc,
                "liner_notes": shelving.notes,
                "callouts": [dict(c) for c in shelving.callouts],
            },
        )

    return AlbumReactions(
        album_id=album_id,
        release_id=str(release_id),
        artist_id=album.artist_id,
        producer=producer_reaction,
        review=review,
        scene_note=scene_note,
        listener=reaction,
        shelving=shelving,
        degraded=tuple(stage for stage in REACTION_STAGES if stage in degraded),
    )


def load_reactions(run_dir: Path, *, album_id: str | None = None) -> list[dict[str, Any]]:
    """Every logged reaction row for a run (optionally one album's), oldest
    first — the read path for publishers and the world renderer."""
    path = Path(run_dir) / f"{STAFF_TABLE}.jsonl"
    if not path.exists():
        return []
    rows = _read_jsonl(path)
    if album_id is not None:
        rows = [r for r in rows if r.get("album_id") == album_id]
    return rows


# --- EXPERIMENT-ONLY: the round-based instrument ------------------------------
# Everything below this line belongs to the pre-album, round-based set
# machinery (`run_staff`: the panel, the cut, the veto, the Critic's naming
# call, the Muse's brief). It survives ONLY as the offline experiment
# instrument behind AFAR_EXPERIMENT_MODE (docs/SPEC.md; DECISIONS 2026-08-03)
# and as the code that reproduces the logged round-based history. It NEVER
# runs on an album: `run_reactions` above is the whole live surface.
#
# The code moved to `afar.staff_rounds`; these names stay importable from here
# because the pre-album conductor and the manual scripts still ask for them.
# The lazy lookup (rather than a top-level re-import) keeps the live module
# free of any import-time dependence on the instrument.

_ROUND_INSTRUMENT: frozenset[str] = frozenset(
    {
        "ArchiveOutcome",
        "BoundaryRecord",
        "SetView",
        "StaffRecord",
        "TakeRow",
        "STAGE_DEGRADED_NOTES",
        "load_recent_tape_titles",
        "load_recent_titles",
        "load_set_view",
        "run_archivist",
        "run_muse_listener",
        "run_staff",
        "take_digest",
    }
)


def __getattr__(name: str) -> Any:
    if name in _ROUND_INSTRUMENT:
        from afar import staff_rounds

        return getattr(staff_rounds, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
