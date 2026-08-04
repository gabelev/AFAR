"""Publish a record to Neon — one artist's ALBUM, or one round-based SET.

The conductor runs on the droplet, where there is no Node toolchain, so the
publish path lives here: media upserts (content-addressed audio bytes), the
rows the web's zod schemas parse, and the compiled world timeline written
STRAIGHT to Neon (`timeline_source`, id 'current', data jsonb), the shape
`web/lib/world/timeline.ts` compiles from. `/api/timeline` prefers that row
over the build-time fixture, so a publish from the droplet reaches production
WITHOUT a rebuild — closing the old "publish recompiles the fixture but a
redeploy is still needed" caveat (DECISIONS.md 2026-07-31).

`publish_album` is the LIVE path (the album is the unit of work,
docs/SPEC.md): one artist's record into a NEW `albums` table, plus its tracks.
`publish_run` / `publish_tape` are the round-based instrument's, unchanged —
they publish the sessions and tapes that are the logged history.

Two rules govern the two shapes living side by side:

  - ONE CATALOGUE, TWO TABLES. Ids are allocated across `releases` and
    `albums` together (`next_catalogue_id`), so the public AFAR-NNNN sequence
    continues without a seam and one slug space resolves either shape.
  - APPEND-ONLY, NEVER REWRITTEN. Releases 0001-0007 and TAPE-0001..0017 keep
    their rows and their numbers exactly as logged. A new shape gets a new
    table precisely so no deployed reader ever meets a row it cannot parse —
    one unparseable row would void the whole live catalogue.

Sources of truth are unchanged (architecture rule 3: the JSONL log under
runs/ is authoritative; Neon is a derived mirror):

  - runs/<id>/album-*.json    — newest by mtime (the album record `run_album`
    wrote: the artist's whole record, content-addressed)
  - runs/<id>/staff.jsonl     — the staff's reactions to a PUBLISHED album
  - runs/<id>/release-*.json  — newest by mtime (the corrected/staff-enriched
    record; the append-only supersede chain writes several)
  - runs/<id>/intents.jsonl   — full DNA per (player, round)
  - runs/<id>/artifacts.jsonl — content hash -> mp3 path

Everything decision-shaped is a pure function (`selected_takes`,
`brief_prose`, `reaction_prose`, `build_release_row`, `build_track_rows`,
`normalized_influence`, `compile_timeline_block`) mirrored one-to-one from
publish_set.mjs / compile_timeline.mjs, so the vitest oracles over there and
the pytest units here pin the same behavior.

DRY-RUN GUARD: `publish_run(dry_run=True)` computes everything and writes
NOTHING — no psycopg import, no network. The conductor forces dry-run
whenever the renderer is mock: mock bytes must never land in the public
media table, the same never-cross-the-streams law as the live-renderer/
mock-embedder guard in scripts/step_b.py.

Requires the `publish` extra for live writes:  uv sync --extra publish
Nothing secret is ever printed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from afar.display import normalize_act_names
from afar.intent import ERAS
from afar.staff import STAGE_NAMES

PLAYER_IDS: tuple[str, ...] = ("silt", "rust", "keep")
SITE = "https://afar.band"

#: The zod default in web (ERAS mirror there) when a logged era index is junk.
_FALLBACK_ERA = "2020s"


# --- env ----------------------------------------------------------------------


def load_database_url(repo_root: Optional[Path] = None) -> Optional[str]:
    """DATABASE_URL from the environment, falling back to kernel/.env.
    Returned, never printed."""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    root = repo_root or Path(__file__).resolve().parents[2]
    env_path = root / "kernel" / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                return value.strip().strip("'\"")
    return None


# --- run log harvesting (ports of the mjs helpers, oracle-pinned) -------------


def publish_preflight(config: Any) -> list[str]:
    """What would stop a finished record from reaching Neon — checked BEFORE
    anything is generated. Returns human-readable reasons, empty when clear.

    A dry publish needs nothing (mock renders never leave the box), so a mock
    conductor and the offline tests are unaffected. A LIVE renderer means real
    money per track, and the failure this guards against is expensive rather
    than merely annoying: AFAR-0008 rendered four paid tracks and only then
    hit `ModuleNotFoundError: psycopg`, because a deploy had synced the
    `listen` extra alone. Import and URL are both cheap; spend is not.
    """
    if getattr(getattr(config, "renderer", None), "name", "mock") == "mock":
        return []
    missing: list[str] = []
    try:
        import psycopg  # noqa: F401
    except ImportError:
        missing.append(
            "psycopg is not installed (deploy with `uv sync --extra dev "
            "--extra listen --extra publish`, or run kernel/ops/install.sh)"
        )
    if not load_database_url():
        missing.append("DATABASE_URL is not set (kernel/.env or the unit's EnvironmentFile)")
    return missing


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def newest_release_record_file(run_dir: Path) -> Optional[Path]:
    """The newest release-*.json by MTIME — the corrected/staff-enriched record,
    never the alphabetically-first one (the release 0002 lesson)."""
    candidates = sorted(
        Path(run_dir).glob("release-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def selected_takes(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The takes to publish: the Producer's cut when the record carries a staff
    block, otherwise the final round's takes, mechanically. pid -> {round, hash}."""
    final_round = record["set"]["rounds"] - 1
    selected = (record.get("staff") or {}).get("producer", {}).get("selected", {})
    out: dict[str, dict[str, Any]] = {}
    for pid in PLAYER_IDS:
        if pid in selected:
            out[pid] = {"round": selected[pid]["round"], "hash": selected[pid]["take_id"]}
        else:
            out[pid] = {"round": final_round, "hash": record["artifacts"][final_round][pid]}
    return out


def brief_prose(staff: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The Muse's words — labeled honestly when carried-forward (composed AFTER
    the release it reads). None keeps the placeholder prose."""
    muse = (staff or {}).get("muse") or {}
    text = muse.get("text")
    if not text:
        return None
    if muse.get("carried_forward"):
        return (
            "What the Muse heard in this release, carried forward into the next "
            f"session: {text}"
        )
    return str(text)


def reaction_prose(staff: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The Listener's words, untouched. None keeps the placeholder."""
    text = ((staff or {}).get("listener") or {}).get("text")
    return str(text) if text else None


def normalized_influence(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The final round's INTENT-space edges, min-max normalized into the
    display schema's [0, 1] (InfluenceEdgeSchema). Kernel edges are signed
    and zero-centred; the legible signal is RELATIVE pull. An isolation set
    can leave no edges — an empty list IS the honest cover."""
    final_round = record["set"]["rounds"] - 1
    edges = (record.get("influence") or {}).get("intent", {}).get(str(final_round), {})
    values = list(edges.values())
    lo = min(values) if values else 0.0
    hi = max(values) if values else 0.0
    span = (hi - lo) or 1.0
    out = []
    for key, value in edges.items():
        to, _, frm = key.partition("<-")
        weight = round(min(1.0, max(0.0, (value - lo) / span)), 4)
        out.append({"from": frm, "to": to, "weight": weight})
    return out


def next_release_id(existing_ids: Iterable[str]) -> str:
    """The next 4-digit catalogue number after the numeric ids already in the
    releases table ('0001' seeded -> '0002' -> …)."""
    numeric = [int(i) for i in existing_ids if str(i).isdigit()]
    return f"{(max(numeric) + 1) if numeric else 1:04d}"


def next_tape_id(existing_ids: Iterable[str]) -> str:
    """The next number in the TAPE-NNNN catalogue series (ids in the tapes
    table are the plain 4 digits; the web prefixes TAPE- for display, the
    same way releases wear AFAR-)."""
    return next_release_id(existing_ids)


def next_catalogue_id(release_ids: Iterable[str], album_ids: Iterable[str]) -> str:
    """The next number in the ONE AFAR-NNNN catalogue series, counted across
    BOTH homes.

    Single-artist albums are stored in their own `albums` table (a new table
    for a new shape — the deployed ReleaseSchema must keep parsing every row
    it already parses, the caution the tapes and import PRs both took), but
    they are NOT a separate catalogue: they continue the same numbering the
    round-based sessions started, so AFAR-0008 follows AFAR-0007 and the
    public sequence has no seam in it. Ids are therefore allocated against the
    union of both tables and can never collide, which is what lets one slug
    space (`/album/afar-NNNN`) resolve either shape.
    """
    return next_release_id([*(str(i) for i in release_ids), *(str(i) for i in album_ids)])


# --- the rows (pure ports of publish_set.mjs main()) --------------------------


def build_release_row(
    release_id: str,
    record: Mapping[str, Any],
    run_id: str,
    take_intents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """The releases-row jsonb, exactly the shape web/lib/data.ts ReleaseSchema
    parses (unknown keys under `metadata` are provenance and stripped on read)."""
    staff = record.get("staff") or None
    degraded = record.get("staff_degraded") or {}

    def _degraded_note(stage: str) -> Optional[str]:
        """The honest sentence a failed staff stage left behind (afar.staff
        STAGE_DEGRADED_NOTES) — preferred over the never-built placeholders."""
        note = (degraded.get(stage) or {}).get("note")
        return str(note) if note else None

    takes = selected_takes(record)
    take_frames = {pid: record["rounds"][takes[pid]["round"]][pid] for pid in PLAYER_IDS}

    # Era: majority vote over the selected takes' DNA (the kernel logs an index).
    era_counts: dict[str, int] = {}
    for pid in PLAYER_IDS:
        idx = take_intents[pid]["intent"].get("era")
        era = ERAS[idx] if isinstance(idx, int) and 0 <= idx < len(ERAS) else _FALLBACK_ERA
        era_counts[era] = era_counts.get(era, 0) + 1
    era = max(era_counts.items(), key=lambda kv: kv[1])[0]

    critic_title = (staff or {}).get("critic", {}).get("release_title")
    release_title = critic_title or f"Untitled Session {release_id}"
    influence = normalized_influence(record)
    date = f"{run_id[0:4]}-{run_id[4:6]}-{run_id[6:8]}"
    condition = record["set"]["condition"]
    hearing = {
        "contact": "each able to hear the others",
        "isolation": "each hearing only itself, doors closed",
        "parallel": "side by side but unable to hear each other",
    }.get(condition, f"condition {condition}")
    numbers = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
               "ten", "eleven", "twelve"]
    rounds_word = (
        numbers[record["set"]["rounds"]]
        if record["set"]["rounds"] < len(numbers)
        else str(record["set"]["rounds"])
    )

    row: dict[str, Any] = {
        "id": release_id,
        "title": release_title,
        "era": era,
        "set": int(release_id) if release_id.isdigit() else 0,
        "condition": condition,
        "date": date,
        "brief": brief_prose(staff)
        or _degraded_note("muse")
        or (
            "No brief this time — the Muse had not yet spoken. The acts went in "
            f"with nothing from outside: {rounds_word} rounds, {hearing}."
        ),
        "selection": (staff or {}).get("producer", {}).get("note")
        or _degraded_note("producer")
        or "The Producer was not yet built, so nothing was cut: these are the last "
        "round's takes, kept automatically.",
        "review": (staff or {}).get("critic", {}).get("release_review")
        or _degraded_note("critic")
        or "The Critic was not yet built. Nobody has judged this or named it — the "
        "chart and the acts' own words are the whole record.",
        "reaction": reaction_prose(staff)
        or _degraded_note("listener")
        or "The Listener was not yet built. Nobody has heard this from the cheap seats yet.",
        "takeIds": [f"{release_id}-{pid}" for pid in PLAYER_IDS],
        "influence": influence,
        "rationales": {pid: take_frames[pid].get("rationale", "") for pid in PLAYER_IDS},
        "metadata": {
            "titlePlaceholder": not critic_title,
            "titledBy": "the Critic" if critic_title else None,
            "briefPlaceholder": not (staff or {}).get("muse"),
            "reviewPlaceholder": not (staff or {}).get("critic"),
            "reactionPlaceholder": not (staff or {}).get("listener"),
            "staffDegraded": degraded or None,
            "museBrief": (staff or {}).get("muse"),
            "listenerReaction": (staff or {}).get("listener"),
            "producerSelection": (
                "the Producer's cut — one take per act, chosen from all rounds by a "
                "three-judge panel reading the log (round per act: "
                + ", ".join(f"{pid}={takes[pid]['round']}" for pid in PLAYER_IDS)
                + ")"
                if (staff or {}).get("producer")
                else (
                    "the Producer did not file this time — the final round's takes "
                    "were published mechanically"
                    if "producer" in degraded
                    else "not built — final round's takes published mechanically"
                )
            ),
            "producerReasoning": (staff or {}).get("producer", {}).get("selected"),
            "criticActReviews": (staff or {}).get("critic", {}).get("act_reviews"),
            "criticTakeTitles": (staff or {}).get("critic", {}).get("take_titles"),
            "runId": run_id,
            "releaseRecordId": record["release_id"],
            "set": record["set"],
            "recordProvenance": record.get("provenance"),
            "influenceDisplay": (
                "final-round INTENT-space graph, min-max normalized to [0,1] for "
                f"InfluenceEdgeSchema (audio-space embedder: {record['set']['embedder']['name']})"
            ),
            "influenceRawByRound": record.get("influence"),
            "convergence": record.get("convergence"),
            "novelty": record.get("novelty"),
            "asymmetry": record.get("asymmetry"),
            "artifactsByRound": record.get("artifacts"),
            "lines": {pid: take_frames[pid].get("line", "") for pid in PLAYER_IDS},
            "publishedBy": "afar.publish (conductor)",
        },
    }
    # The Archivist's liner notes — back-of-sleeve prose, first-class on the
    # page, optional in the schema so every pre-Archivist row keeps parsing.
    archivist = (staff or {}).get("archivist") or {}
    if archivist.get("liner_notes"):
        row["linerNotes"] = normalize_act_names(str(archivist["liner_notes"]))
        row["metadata"]["linerNotesBy"] = "the Archivist"
    valence = (staff or {}).get("listener", {}).get("valence")
    if valence:
        row["reactionValence"] = valence
    if (staff or {}).get("producer", {}).get("selected"):
        row["selections"] = {pid: f"{release_id}-{pid}" for pid in PLAYER_IDS}
    reviews = (staff or {}).get("critic", {}).get("act_reviews")
    if reviews:
        row["reviews"] = reviews
    return row


def build_track_rows(
    release_id: str,
    record: Mapping[str, Any],
    take_intents: Mapping[str, Mapping[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    """The tracks-row jsonb per act — TrackSchema plus provenance keys."""
    staff = record.get("staff") or {}
    takes = selected_takes(record)
    release_title = staff.get("critic", {}).get("release_title") or f"Untitled Session {release_id}"
    take_titles = staff.get("critic", {}).get("take_titles", {})
    rows = []
    for pid in PLAYER_IDS:
        row = take_intents[pid]
        rows.append(
            {
                "id": f"{release_id}-{pid}",
                "releaseId": release_id,
                "agentId": pid,
                "title": take_titles.get(pid)
                or f"{release_title} — {STAGE_NAMES.get(pid, pid)}'s take",
                # The set's take length (the Producer's direction); 30 for
                # every record written before lengths were variable.
                "durationSec": int(record.get("set", {}).get("duration_s", 30)),
                "audioUrl": f"/api/media/{takes[pid]['hash']}",
                # provenance (stripped by data.ts on read)
                "titledBy": "the Critic" if take_titles.get(pid) else None,
                "line": row.get("line", ""),
                "intent": row.get("intent", {}),
                "round": takes[pid]["round"],
                "runId": run_id,
            }
        )
    return rows


# --- the timeline (pure port of compile_timeline.mjs) -------------------------


def timeline_staff(record: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """The staff's logged rows for the world's staged staff events — the
    TimelineStaff shape web/lib/world/timeline.ts compiles (Producer walks
    the direction to the studios, Critic delivers verdicts, Listener reacts
    in the archive armchair, Muse posts the theme at the window). Every
    field is a logged word, through the same display shim as the acts'
    lines; a degraded or pre-staff stage has no entry and the world stages
    nothing for it. Mirrors compileStaff() in compile_timeline.mjs 1:1 —
    the shared oracle in test_publish.py / publish_set.test.ts pins both.
    """
    src = record.get("staff") or {}
    staff: dict[str, Any] = {}
    producer_note = (src.get("producer") or {}).get("note")
    if producer_note:
        staff["producer"] = {"note": normalize_act_names(str(producer_note))}
    critic: dict[str, Any] = {}
    release_review = (src.get("critic") or {}).get("release_review")
    if release_review:
        critic["releaseReview"] = normalize_act_names(str(release_review))
    act_reviews = {
        pid: normalize_act_names(str(text))
        for pid, text in ((src.get("critic") or {}).get("act_reviews") or {}).items()
        if pid in PLAYER_IDS and text
    }
    if act_reviews:
        critic["actReviews"] = act_reviews
    if critic:
        staff["critic"] = critic
    muse = src.get("muse") or {}
    if muse.get("theme") or muse.get("text"):
        entry: dict[str, Any] = {}
        if muse.get("theme"):
            entry["theme"] = normalize_act_names(str(muse["theme"]))
        if muse.get("text"):
            entry["text"] = normalize_act_names(str(muse["text"]))
        staff["muse"] = entry
    listener = src.get("listener") or {}
    if listener.get("text"):
        entry = {}
        if listener.get("valence"):
            entry["valence"] = listener["valence"]
        entry["text"] = normalize_act_names(str(listener["text"]))
        staff["listener"] = entry
    return staff or None


def compile_timeline_block(
    release_id: str,
    row: Mapping[str, Any],
    run_id: str,
    runs_root: Path,
) -> Optional[dict[str, Any]]:
    """One world set-block from a release row + its run's newest release record.
    Exactly the TimelineSource shape web/lib/world/timeline.ts expects.
    Returns None when the run dir has no release record."""
    run_dir = Path(runs_root) / run_id
    record_file = newest_release_record_file(run_dir)
    if record_file is None:
        return None
    record = json.loads(record_file.read_text(encoding="utf-8"))
    rounds = record["set"]["rounds"]

    lines_by_round = []
    for r in range(rounds):
        frames = record["rounds"][r]
        entry = {}
        for pid in PLAYER_IDS:
            line = (frames.get(pid) or {}).get("line")
            if not line:
                raise ValueError(f"run {run_id} round {r} is missing {pid}'s line")
            # Display shim: pre-voice-fix sets say "Rust"/"Keep"/"Silt"; show
            # first names (mirrors compile_timeline.mjs; no-op post-fix).
            entry[pid] = normalize_act_names(line)
        lines_by_round.append(entry)

    era = row.get("era")
    set_number = row.get("set")
    staff = timeline_staff(record)
    return {
        **({"staff": staff} if staff else {}),
        "runId": run_id,
        "releaseRecordId": record["release_id"],
        "releaseId": release_id,
        "title": row.get("title") or f"AFAR-{release_id}",
        "era": era if era in ERAS else _FALLBACK_ERA,
        "set": set_number if isinstance(set_number, int) else int(release_id),
        # The log is authoritative for the condition; the row mirrors it.
        "condition": record["set"].get("condition") or row.get("condition"),
        "rounds": rounds,
        "names": dict(STAGE_NAMES),
        "linesByRound": lines_by_round,
        "artifactsByRound": record["artifacts"],
        "intentEdgesByRound": record["influence"]["intent"],
    }


def compile_timeline_blocks(
    release_rows: Sequence[tuple[str, Mapping[str, Any]]],
    runs_root: Path,
) -> dict[str, Any]:
    """The whole catalogue as ordered set-blocks (oldest release first), the
    `timeline_source.data` payload. Rows without a runId (the seeded 0001) or
    with a missing run dir are skipped — same rules as compile_timeline.mjs."""
    blocks = []
    for release_id, row in sorted(release_rows, key=lambda kv: str(kv[0])):
        run_id = ((row.get("metadata") or {}).get("runId")) if isinstance(row, Mapping) else None
        if not run_id:
            continue
        if not (Path(runs_root) / run_id).is_dir():
            continue
        block = compile_timeline_block(str(release_id), row, str(run_id), runs_root)
        if block is not None:
            blocks.append(block)
    return {"blocks": blocks}


# --- the album: ONE artist's record (the live spine) --------------------------


def newest_album_record_file(run_dir: Path) -> Optional[Path]:
    """The run's newest album-*.json by mtime — what `run_album` wrote."""
    candidates = sorted(
        Path(run_dir).glob("album-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def album_track_id(release_id: str, index: int) -> str:
    """`0008-01` — a track's public id. Position-based rather than act-based
    (the sessions' `0001-silt`) because an album is one artist's whole record:
    every track shares the artist, so the tracklist POSITION is the thing that
    distinguishes them, and it never changes for a published record."""
    return f"{release_id}-{index + 1:02d}"


def album_era(record: Mapping[str, Any]) -> str:
    """The record's era: majority vote over its own tracks' DNA, ties to the
    earliest song (same rule the sessions use over the selected takes)."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for track in (record.get("album") or {}).get("tracks") or ():
        idx = (track.get("intent") or {}).get("era")
        era = ERAS[idx] if isinstance(idx, int) and 0 <= idx < len(ERAS) else _FALLBACK_ERA
        if era not in counts:
            order.append(era)
        counts[era] = counts.get(era, 0) + 1
    if not counts:
        return _FALLBACK_ERA
    return max(order, key=lambda era: counts[era])


def album_influence(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The record's INTENT-space influence edges, min-max normalized into the
    display range [0, 1] — the same treatment the sessions' final-round graph
    gets, at album cadence.

    Edges run heard artist -> the recording artist: "how much did that record
    pull this one". A debut (nothing heard, or nothing measurable) yields an
    empty list, which is the honest cover for a first record.
    """
    influence = ((record.get("features") or {}).get("intent") or {}).get("influence") or {}
    artist_by_album = {
        str(h.get("album_id", "")): str(h.get("artist_id", ""))
        for h in record.get("heard") or ()
        if isinstance(h, Mapping)
    }
    values = [float(v) for v in influence.values()]
    lo, hi = (min(values), max(values)) if values else (0.0, 0.0)
    span = (hi - lo) or 1.0
    to = str(record.get("artist_id", ""))
    edges = []
    for album_id, value in influence.items():
        frm = artist_by_album.get(str(album_id), "")
        if not frm or frm == to:
            continue
        edges.append(
            {
                "from": frm,
                "to": to,
                "weight": round(min(1.0, max(0.0, (float(value) - lo) / span)), 4),
            }
        )
    return edges


def reactions_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The staff's logged album-reaction rows -> the same block shape
    `afar.staff.AlbumReactions.to_row()` returns.

    The LOG is what the publisher reads, never the object the staff pass
    ran returned (architecture rule 3), so a republish of an old run puts the
    same words back on the sleeve. Newest row per stage wins; a stage with no
    row simply is not there, and its `staff_stage_failed` note (if any) rides
    under `degraded` so the page can say so honestly.
    """
    block: dict[str, Any] = {}
    degraded: dict[str, str] = {}
    by_kind = {
        "producer_reaction": "producer",
        "album_review": "critic",
        "scene_note": "muse",
        "listener_reaction": "listener",
        "shelving": "archivist",
    }
    for row in rows:
        kind = str(row.get("kind", ""))
        if kind == "staff_stage_failed":
            stage = str(row.get("stage") or row.get("agent") or "")
            if stage and row.get("note"):
                degraded[stage] = str(row["note"])
            continue
        stage = by_kind.get(kind)
        if stage is None:
            continue
        entry = {k: v for k, v in row.items() if k not in _LOG_STAMPS}
        block[stage] = entry
        degraded.pop(stage, None)
    if degraded:
        block["degraded"] = degraded
    return block


#: Row keys that are provenance, not content — stripped when a logged staff
#: row becomes a sleeve block.
_LOG_STAMPS: frozenset[str] = frozenset(
    {"ts", "run_id", "code_sha", "seed", "renderer_version", "prompt_sha",
     "kind", "agent", "album_id", "release_id", "artist", "condition"}
)


def build_album_row(
    release_id: str,
    record: Mapping[str, Any],
    run_id: str,
    *,
    reactions: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """The albums-row jsonb — the shape `web/lib/data.ts` AlbumRecordSchema
    parses. A NEW table and a NEW schema: no releases row ever meets a shape
    it cannot parse (the tapes/import precedent).

    Attribution is FIRST-CLASS: `artistId` is a required top-level field, not
    an inference from the tracklist, because an album belongs to one artist —
    that is the whole spine (docs/SPEC.md).

    The artist's own `description` is the sleeve text. It sits where the
    Critic's release title and the Producer's selection note used to sit,
    because the artist names and frames its own work now and the staff only
    react. `reactions` (the logged staff block) is optional and additive: the
    record publishes the moment it exists, and the commentary lands on the
    superseding write a beat later.
    """
    body = record.get("album") or {}
    tracks = record.get("tracks") or []
    row: dict[str, Any] = {
        "id": release_id,
        "kind": "album",
        "title": str(body.get("title", "")),
        "artistId": str(record.get("artist_id", "")),
        "description": str(body.get("description", "")),
        "date": f"{run_id[0:4]}-{run_id[4:6]}-{run_id[6:8]}",
        "era": album_era(record),
        "trackIds": [album_track_id(release_id, i) for i in range(len(tracks))],
        "influence": album_influence(record),
        "heard": [
            {
                "albumId": str(h.get("album_id", "")),
                "artistId": str(h.get("artist_id", "")),
                "title": str(h.get("title", "")),
            }
            for h in record.get("heard") or ()
            if isinstance(h, Mapping)
        ],
        "metadata": {
            "runId": run_id,
            "albumId": str(record.get("album_id", "")),
            "albumRecordId": str(record.get("record_id", "")),
            "session": record.get("session"),
            "features": record.get("features"),
            "isolated": bool((record.get("session") or {}).get("isolated", False)),
            "publishedBy": "afar.publish (the album loop)",
        },
    }
    return apply_reactions(row, reactions)


def apply_reactions(
    row: dict[str, Any], reactions: Optional[Mapping[str, Any]]
) -> dict[str, Any]:
    """Hang the staff's reactions off a published album row.

    Additive, never destructive: nothing the staff said can change the title,
    the description, the tracklist or the artist — the record was already out
    when the first reaction was written (architecture rule 1). A stage that
    degraded leaves its honest note under `staffDegraded` and no prose at all.
    """
    if not reactions:
        return row
    degraded = dict(reactions.get("degraded") or {})

    def _text(stage: str, *keys: str) -> Optional[str]:
        entry = reactions.get(stage) or {}
        for key in keys:
            value = entry.get(key)
            if value:
                return normalize_act_names(str(value))
        return None

    producer = _text("producer", "text")
    if producer:
        row["producerNote"] = producer
    review = _text("critic", "text", "verdict")
    if review:
        row["review"] = review
    track_notes = (reactions.get("critic") or {}).get("track_notes") or {}
    if track_notes:
        row["trackNotes"] = {
            str(k): normalize_act_names(str(v)) for k, v in track_notes.items() if v
        }
    scene = _text("muse", "text", "body")
    if scene:
        row["sceneNote"] = scene
    theme = (reactions.get("muse") or {}).get("theme")
    if theme:
        row["sceneTheme"] = normalize_act_names(str(theme))
    reaction = _text("listener", "text")
    if reaction:
        row["reaction"] = reaction
    valence = (reactions.get("listener") or {}).get("valence")
    if valence:
        row["reactionValence"] = str(valence)
    liner = _text("archivist", "liner_notes", "notes")
    if liner:
        row["linerNotes"] = liner
    placement = (reactions.get("archivist") or {}).get("placement")
    if placement:
        row["metadata"]["placement"] = str(placement)
    if degraded:
        row["staffDegraded"] = degraded
    return row


def build_album_track_rows(
    release_id: str, record: Mapping[str, Any], run_id: str
) -> list[dict[str, Any]]:
    """One tracks row per song — TrackSchema plus provenance keys. Every track
    on an album carries the same `agentId`: the artist whose record it is."""
    artist_id = str(record.get("artist_id", ""))
    body = record.get("album") or {}
    dna_by_index = {
        i: (t.get("intent") or {}) for i, t in enumerate(body.get("tracks") or ())
    }
    rows = []
    for i, track in enumerate(record.get("tracks") or ()):
        rows.append(
            {
                "id": album_track_id(release_id, i),
                "releaseId": release_id,
                "agentId": artist_id,
                "title": str(track.get("title", "")),
                "durationSec": int(track.get("duration_s", 0)) or None,
                "audioUrl": f"/api/media/{track.get('hash', '')}",
                # provenance (stripped by data.ts on read)
                "trackIndex": i,
                "line": normalize_act_names(str(track.get("note", ""))),
                "intent": dna_by_index.get(i, {}),
                "runId": run_id,
                "albumId": str(record.get("album_id", "")),
            }
        )
    return rows


@dataclass(frozen=True)
class AlbumPublishOutcome:
    """What one album publish did (or, dry, would have done)."""

    release_id: str
    run_id: str
    artist_id: str
    title: str
    dry_run: bool
    tracks: int = 0
    media_bytes: int = 0
    track_ids: tuple[str, ...] = ()
    timeline_blocks: int = 0
    reacted: bool = False  # True when the staff's reactions rode this write


def _album_id_for_run(conn: Any, run_id: str) -> Optional[str]:
    """A run's already-published catalogue id, if any — republish (the second
    hop, once the staff have reacted) keeps the same number."""
    for row_id, data in conn.execute("SELECT id, data FROM albums").fetchall():
        if _as_mapping(data).get("metadata", {}).get("runId") == run_id:
            return str(row_id)
    return None


def publish_album(
    run_dir: Path,
    *,
    release_id: Optional[str] = None,
    db_url: Optional[str] = None,
    dry_run: bool = False,
    connection: Any = None,
) -> AlbumPublishOutcome:
    """Publish ONE artist's record: media -> tracks -> albums row -> timeline.

    Everything is read from the run's own log (architecture rule 3): the album
    record `run_album` wrote, the artifact rows for the audio, and the staff's
    logged reaction rows if any exist yet. Idempotent — a run keeps its
    catalogue number — which is what makes the two-hop publish safe: the
    record goes out the moment it exists, the staff react to a record that is
    already public, and a second call re-writes the same row with their words
    on it.

    `dry_run=True` computes everything and writes NOTHING (no psycopg import,
    no network) — the conductor forces it whenever the renderer is mock.
    """
    from afar.staff import load_reactions

    run_dir = Path(run_dir)
    run_id = run_dir.name
    runs_root = run_dir.parent

    record_file = newest_album_record_file(run_dir)
    if record_file is None:
        raise FileNotFoundError(f"no album-*.json under {run_dir}")
    record = json.loads(record_file.read_text(encoding="utf-8"))
    album_id = str(record.get("album_id", ""))

    artifact_paths = {a["hash"]: a["path"] for a in read_jsonl(run_dir / "artifacts.jsonl")}
    audio: dict[str, bytes] = {}
    for track in record.get("tracks") or ():
        digest = str(track.get("hash", ""))
        file = artifact_paths.get(digest)
        if not file:
            raise ValueError(f"no artifact row for hash {digest}")
        data = _resolve_audio(file, runs_root).read_bytes()
        if len(data) < 1000:
            raise ValueError(f"suspiciously small mp3 for track {digest}: {len(data)} bytes")
        audio[digest] = data

    reactions = reactions_from_rows(load_reactions(run_dir, album_id=album_id))

    if dry_run:
        rid = release_id or "0000"
        row = build_album_row(rid, record, run_id, reactions=reactions)
        track_rows = build_album_track_rows(rid, record, run_id)
        return AlbumPublishOutcome(
            release_id=rid,
            run_id=run_id,
            artist_id=row["artistId"],
            title=row["title"],
            dry_run=True,
            tracks=len(track_rows),
            media_bytes=sum(len(b) for b in audio.values()),
            track_ids=tuple(t["id"] for t in track_rows),
            reacted=bool(reactions),
        )

    conn = connection
    if conn is None:
        import psycopg

        url = db_url or load_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL not set and not found in kernel/.env")
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg.connect(url)

    try:
        jsonb = _jsonb_for(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS media "
            "(id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)"
        )
        for table in ("releases", "albums", "tracks", "timeline_source"):
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id text PRIMARY KEY, data jsonb NOT NULL)"
            )

        if release_id is None:
            release_id = _album_id_for_run(conn, run_id)
        if release_id is None:
            release_ids = [r[0] for r in conn.execute("SELECT id FROM releases").fetchall()]
            album_ids = [r[0] for r in conn.execute("SELECT id FROM albums").fetchall()]
            release_id = next_catalogue_id(release_ids, album_ids)

        row = build_album_row(release_id, record, run_id, reactions=reactions)
        track_rows = build_album_track_rows(release_id, record, run_id)

        for digest, data in audio.items():
            conn.execute(
                "INSERT INTO media (id, content_type, bytes) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, "
                "bytes = EXCLUDED.bytes",
                (digest, "audio/mpeg", data),
            )
        for track in track_rows:
            conn.execute(
                "INSERT INTO tracks (id, data) VALUES (%s, %s) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (track["id"], jsonb(track)),
            )
        conn.execute(
            "INSERT INTO albums (id, data) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            (release_id, jsonb(row)),
        )

        # The world's timeline still compiles from the ROUND-BASED releases —
        # the town's staged walks are a round-based grammar (rounds, per-act
        # lines, the archive walk) and an album has none of it. Recompiling
        # here keeps the row fresh and valid across an album publish; staging
        # albums in the world is its own design round (DECISIONS.md).
        all_rows = conn.execute("SELECT id, data FROM releases ORDER BY id").fetchall()
        timeline = compile_timeline_blocks(
            [(r[0], _as_mapping(r[1])) for r in all_rows], runs_root
        )
        conn.execute(
            "INSERT INTO timeline_source (id, data) VALUES ('current', %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            (jsonb(timeline),),
        )
        conn.commit()
    finally:
        if connection is None:
            conn.close()

    return AlbumPublishOutcome(
        release_id=release_id,
        run_id=run_id,
        artist_id=row["artistId"],
        title=row["title"],
        dry_run=False,
        tracks=len(track_rows),
        media_bytes=sum(len(b) for b in audio.values()),
        track_ids=tuple(t["id"] for t in track_rows),
        timeline_blocks=len(timeline["blocks"]),
        reacted=bool(reactions),
    )


# --- the tape (the vault doctrine: the session's FULL tape releases) ----------


def build_tape_row(
    tape_id: str,
    view: Any,  # afar.archive.TapeView (typed loose to keep this module light)
    shelving: Optional[Mapping[str, Any]],
    *,
    release_id: Optional[str] = None,
) -> dict[str, Any]:
    """The tapes-row jsonb — the shape web/lib/data.ts TapeSchema parses.

    `view` is the session read whole from the log; `shelving` is the
    Archivist's newest logged `archives` row (placement, arc, callouts, liner
    notes). A tape can publish unshelved (Archivist degraded): the takes
    stand, the framing fields stay absent, honestly. Display shim: logged
    lines and quoted prose go through normalize_act_names (pre-voice-fix
    sessions say "Rust"/"Keep"/"Silt"; the tape shows first names)."""
    shelving = shelving or {}
    staff = (view.record or {}).get("staff") or {}
    take_titles = staff.get("critic", {}).get("take_titles", {})

    # The Archivist's callouts, keyed back to (player, round) — the row may
    # name the act by stage name or by id; both resolve.
    names_to_ids = {name: pid for pid, name in STAGE_NAMES.items()}
    callout_by: dict[tuple[str, int], str] = {}
    for c in shelving.get("callouts", ()):
        pid = names_to_ids.get(str(c.get("act", "")), str(c.get("act", "")))
        if c.get("round") is not None and c.get("note"):
            callout_by[(pid, int(c["round"]))] = normalize_act_names(str(c["note"]))

    takes: list[dict[str, Any]] = []
    for t in view.takes:
        selected = view.selected.get(t.player) == t.round
        entry: dict[str, Any] = {
            "round": t.round,
            "agentId": t.player,
            "title": take_titles.get(t.player) if selected else None,
            "audioUrl": f"/api/media/{t.take_id}",
            "durationSec": int(view.duration_s),
            "selected": selected,
            "line": normalize_act_names(t.line),
        }
        callout = callout_by.get((t.player, t.round))
        if callout:
            entry["callout"] = callout
        dissents = [
            f"the {d.get('judge', 'panel')} judge wanted this one on the release"
            for d in view.dissents.get(t.player, ())
            if d.get("preferred_round") == t.round
        ]
        if dissents:
            entry["dissent"] = "; ".join(dissents)
        takes.append(entry)

    row: dict[str, Any] = {
        "id": tape_id,
        "kind": "tape",
        "title": normalize_act_names(str(shelving.get("tape_title") or f"Session Tape {tape_id}")),
        "runId": view.run_id,
        "releaseId": release_id,
        "date": view.date,
        "condition": view.condition,
        "rounds": int(view.rounds),
        "status": view.status,
        "takes": takes,
        "metadata": {
            "players": list(view.players),
            "complete": view.complete,
            "releaseRecordId": (view.record or {}).get("release_id"),
            "publishedBy": "afar.publish (the Archivist's shelf)",
        },
    }
    if shelving.get("placement"):
        row["placement"] = str(shelving["placement"])
    if shelving.get("arc"):
        row["arc"] = normalize_act_names(str(shelving["arc"]))
    if shelving.get("liner_notes"):
        row["linerNotes"] = normalize_act_names(str(shelving["liner_notes"]))
    if view.veto_note:
        row["vetoNote"] = normalize_act_names(str(view.veto_note))
    return row


def _read_all_audio(run_dir: Path, runs_root: Path) -> dict[str, bytes]:
    """EVERY take's bytes for this run, keyed by content hash — the vault
    doctrine's media upload (all takes, not just the cut; ~23MB/set)."""
    audio: dict[str, bytes] = {}
    for a in read_jsonl(Path(run_dir) / "artifacts.jsonl"):
        data = _resolve_audio(a["path"], runs_root).read_bytes()
        if len(data) < 1000:
            raise ValueError(f"suspiciously small mp3 for take {a['hash']}: {len(data)} bytes")
        audio[a["hash"]] = data
    return audio


def _tape_id_for_run(conn: Any, run_id: str) -> Optional[str]:
    """A run's already-published tape id, if any — republish stays idempotent."""
    rows = conn.execute("SELECT id, data FROM tapes").fetchall()
    for row_id, data in rows:
        if _as_mapping(data).get("runId") == run_id:
            return str(row_id)
    return None


@dataclass(frozen=True)
class TapeOutcome:
    """What one tape publish did (or, dry, would have done)."""

    tape_id: str
    run_id: str
    title: str
    dry_run: bool
    takes: int = 0
    media_bytes: int = 0
    shelved: bool = True  # False when the tape published unshelved (degraded)


def publish_tape(
    run_dir: Path,
    *,
    release_id: Optional[str] = None,
    tape_id: Optional[str] = None,
    db_url: Optional[str] = None,
    dry_run: bool = False,
    connection: Any = None,
) -> TapeOutcome:
    """Publish one session's FULL tape: every take's audio (content-addressed
    upserts) plus the tapes row. Works for ANY run — released (pass its
    release_id so the tape points home), vetoed, abandoned, or solo. The tape
    publishes even unshelved (no `archives` row yet): the framing fields stay
    absent, the takes stand. Idempotent: a run's tape keeps its id."""
    from afar.archive import load_tape_view, newest_shelving

    run_dir = Path(run_dir)
    runs_root = run_dir.parent
    view = load_tape_view(run_dir)
    shelving = newest_shelving(run_dir)
    audio = _read_all_audio(run_dir, runs_root)

    if dry_run:
        row = build_tape_row(tape_id or "0000", view, shelving, release_id=release_id)
        return TapeOutcome(
            tape_id=row["id"],
            run_id=view.run_id,
            title=row["title"],
            dry_run=True,
            takes=len(row["takes"]),
            media_bytes=sum(len(b) for b in audio.values()),
            shelved=shelving is not None,
        )

    conn = connection
    if conn is None:
        import psycopg

        url = db_url or load_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL not set and not found in kernel/.env")
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg.connect(url)
    try:
        jsonb = _jsonb_for(conn)
        outcome = _write_tape(
            conn, jsonb, view, shelving, audio, release_id=release_id, tape_id=tape_id
        )
        conn.commit()
    finally:
        if connection is None:
            conn.close()
    return outcome


def _write_tape(
    conn: Any,
    jsonb: Any,
    view: Any,
    shelving: Optional[Mapping[str, Any]],
    audio: Mapping[str, bytes],
    *,
    release_id: Optional[str] = None,
    tape_id: Optional[str] = None,
) -> TapeOutcome:
    """The tape write, on an open connection (shared by publish_run)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS media "
        "(id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS tapes (id text PRIMARY KEY, data jsonb NOT NULL)")
    for content_hash, data in audio.items():
        conn.execute(
            "INSERT INTO media (id, content_type, bytes) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, "
            "bytes = EXCLUDED.bytes",
            (content_hash, "audio/mpeg", data),
        )
    if tape_id is None:
        tape_id = _tape_id_for_run(conn, view.run_id)
    if tape_id is None:
        rows = conn.execute("SELECT id FROM tapes").fetchall()
        tape_id = next_tape_id(r[0] for r in rows)
    row = build_tape_row(tape_id, view, shelving, release_id=release_id)
    conn.execute(
        "INSERT INTO tapes (id, data) VALUES (%s, %s) "
        "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
        (tape_id, jsonb(row)),
    )
    return TapeOutcome(
        tape_id=tape_id,
        run_id=view.run_id,
        title=row["title"],
        dry_run=False,
        takes=len(row["takes"]),
        media_bytes=sum(len(b) for b in audio.values()),
        shelved=shelving is not None,
    )


# --- publish ------------------------------------------------------------------


@dataclass(frozen=True)
class PublishOutcome:
    """What one publish did (or, dry, would have done). Never carries secrets."""

    release_id: str
    run_id: str
    release_title: str
    dry_run: bool
    media: dict[str, int] = field(default_factory=dict)  # pid -> byte count
    track_ids: tuple[str, ...] = ()
    timeline_blocks: int = 0
    tape: Optional[TapeOutcome] = None  # the session tape (the vault doctrine)


def _resolve_audio(path_str: str, runs_root: Path) -> Path:
    """The logged artifact path is authoritative; if the run was copied between
    machines the content-addressed basename under runs/audio still resolves."""
    p = Path(path_str)
    if p.is_file():
        return p
    fallback = Path(runs_root) / "audio" / p.name
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"audio file not found: {path_str} (or runs/audio/{p.name})")


def publish_run(
    run_dir: Path,
    *,
    release_id: Optional[str] = None,
    db_url: Optional[str] = None,
    dry_run: bool = False,
    connection: Any = None,
) -> PublishOutcome:
    """Publish one completed run: media -> tracks -> release -> timeline_source.

    Idempotent (upserts keyed on id). `dry_run=True` computes everything and
    touches NOTHING external — no psycopg import, no bytes read beyond the
    local run. `connection` injects a DB connection for tests; live callers
    leave it None and need the `publish` extra (psycopg[binary]).
    """
    run_dir = Path(run_dir)
    run_id = run_dir.name
    runs_root = run_dir.parent

    record_file = newest_release_record_file(run_dir)
    if record_file is None:
        raise FileNotFoundError(f"no release-*.json under {run_dir}")
    record = json.loads(record_file.read_text(encoding="utf-8"))
    takes = selected_takes(record)

    intent_rows = read_jsonl(run_dir / "intents.jsonl")
    take_intents: dict[str, Mapping[str, Any]] = {}
    for pid in PLAYER_IDS:
        match = next(
            (r for r in intent_rows if r["player"] == pid and r["round"] == takes[pid]["round"]),
            None,
        )
        if match is None:
            raise ValueError(f"selected take is missing player {pid}")
        take_intents[pid] = match

    artifact_paths = {
        a["hash"]: a["path"] for a in read_jsonl(run_dir / "artifacts.jsonl")
    }
    audio: dict[str, bytes] = {}
    for pid in PLAYER_IDS:
        file = artifact_paths.get(takes[pid]["hash"])
        if not file:
            raise ValueError(f"no artifact row for hash {takes[pid]['hash']}")
        data = _resolve_audio(file, runs_root).read_bytes()
        if len(data) < 1000:
            raise ValueError(f"suspiciously small mp3 for {pid}: {len(data)} bytes")
        audio[pid] = data

    if dry_run:
        rid = release_id or "0000"
        release_row = build_release_row(rid, record, run_id, take_intents)
        track_rows = build_track_rows(rid, record, take_intents, run_id)
        block = compile_timeline_block(rid, release_row, run_id, runs_root)
        return PublishOutcome(
            release_id=rid,
            run_id=run_id,
            release_title=release_row["title"],
            dry_run=True,
            media={pid: len(audio[pid]) for pid in PLAYER_IDS},
            track_ids=tuple(t["id"] for t in track_rows),
            timeline_blocks=1 if block else 0,
            tape=publish_tape(run_dir, release_id=rid, dry_run=True),
        )

    conn = connection
    if conn is None:
        import psycopg

        url = db_url or load_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL not set and not found in kernel/.env")
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg.connect(url)

    try:
        jsonb = _jsonb_for(conn)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS media "
            "(id text PRIMARY KEY, content_type text NOT NULL, bytes bytea NOT NULL)"
        )
        for table in ("releases", "tracks", "timeline_source"):
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id text PRIMARY KEY, data jsonb NOT NULL)"
            )

        if release_id is None:
            rows = conn.execute("SELECT id FROM releases").fetchall()
            release_id = next_release_id(r[0] for r in rows)
        release_row = build_release_row(release_id, record, run_id, take_intents)
        track_rows = build_track_rows(release_id, record, take_intents, run_id)

        for pid in PLAYER_IDS:
            conn.execute(
                "INSERT INTO media (id, content_type, bytes) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET content_type = EXCLUDED.content_type, "
                "bytes = EXCLUDED.bytes",
                (takes[pid]["hash"], "audio/mpeg", audio[pid]),
            )
        for track in track_rows:
            conn.execute(
                "INSERT INTO tracks (id, data) VALUES (%s, %s) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (track["id"], jsonb(track)),
            )
        conn.execute(
            "INSERT INTO releases (id, data) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            (release_id, jsonb(release_row)),
        )

        # The world's timeline, recompiled over the WHOLE catalogue and written
        # to Neon — /api/timeline prefers this row, so no rebuild is needed.
        all_rows = conn.execute("SELECT id, data FROM releases ORDER BY id").fetchall()
        release_rows = [(r[0], _as_mapping(r[1])) for r in all_rows]
        timeline = compile_timeline_blocks(release_rows, runs_root)
        conn.execute(
            "INSERT INTO timeline_source (id, data) VALUES ('current', %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            (jsonb(timeline),),
        )

        # The vault opens: EVERY take's audio and the session's full tape ride
        # the same publish (the Archivist may have degraded — the tape still
        # ships, unshelved and honest).
        from afar.archive import load_tape_view, newest_shelving

        tape_outcome = _write_tape(
            conn,
            jsonb,
            load_tape_view(run_dir),
            newest_shelving(run_dir),
            _read_all_audio(run_dir, runs_root),
            release_id=release_id,
        )
        conn.commit()
    finally:
        if connection is None:
            conn.close()

    return PublishOutcome(
        release_id=release_id,
        run_id=run_id,
        release_title=release_row["title"],
        dry_run=False,
        media={pid: len(audio[pid]) for pid in PLAYER_IDS},
        track_ids=tuple(t["id"] for t in track_rows),
        timeline_blocks=len(timeline["blocks"]),
        tape=tape_outcome,
    )


def _jsonb_for(conn: Any):
    """The jsonb wrapper for a connection of UNKNOWN provenance: a real
    psycopg connection (whoever opened it) gets Jsonb; injected test fakes
    take raw dicts. The retrospective script passes its own psycopg
    connection into publish_tape — the `connection is None` heuristic alone
    mis-classified it (the observed 'cannot adapt type dict' crash)."""
    try:
        import psycopg
        from psycopg.types.json import Jsonb

        if isinstance(conn, psycopg.Connection):
            return Jsonb
    except ImportError:
        pass
    return lambda value: value


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """Rows come back as dicts from psycopg's jsonb loader; injected test
    connections may hand back JSON strings."""
    if isinstance(value, str):
        return json.loads(value)
    return value
