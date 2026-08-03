"""The orchestrators: `run_album` (the piece) and `run_set` (the experiment).

`run_album` is the live spine (docs/SPEC.md): one artist, one record. It
builds what that artist has heard through the ONE chokepoint
(`build_album_context` — no staff channel), asks for the whole album in a
single call, renders every track deterministically from its own DNA, embeds
each track in both spaces, computes the album-cadence features against the
records it heard, and logs all of it append-only. It returns an `AlbumResult`
the conductor can publish.

`run_set` below is the round-based experiment instrument, kept whole behind
`AFAR_EXPERIMENT_MODE`: the published round-based history stands as logged,
and the Ensemble Effect still needs per-round contact/isolation/parallel.

--- run_set: three players, N rounds, cross-perception, one interaction record.

The Step B orchestrator — the first thing that is actually the piece. Each
round it builds every player's context (`build_context`, the single condition
chokepoint), runs all three PERCEIVE -> DECIDE -> EXECUTE loops, embeds every
rendered track in BOTH spaces (audio via the injected AudioEmbedder, intent
via `features.intent_vector`), and logs perceptions / intents / artifacts /
embeddings as first-class rows. In contact sets each round's takes are also
MEASURED (`afar.perception.ear`, right after embedding — DSP facts plus
relations over the very vectors just logged), so next round's contexts can
tell each act what the other takes actually sounded like. After the last round it computes the
interaction features — influence graph per round, convergence curve, novelty,
asymmetry, in both spaces — logs them, and emits a content-addressed release
record: the set reduced to the facts a cover, a listener, or an analysis can
be built from.

Scheduling is part of the manipulation: contact and parallel run the three
players simultaneously (`ensemble.pipeline.fan_out`), isolation runs them
sequentially. Combined with `build_context`, that lets the analysis separate
"being run together" (parallel) from "hearing each other" (contact).

Logging always happens on the orchestrator thread, in stable player order,
AFTER a round's fan-out has fully collected — the append-only ledger must
never be written from worker threads, and row order in the JSONL files should
be a fact of the schedule, not of thread timing.

Reproducibility: per-(player, round) seeds are derived from the set seed by
hash offset, so the same set seed replays the same set — the release record's
content hash is the proof.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from ensemble.agent import Artifact, Decision
from ensemble.pipeline import Stage, fan_out

from afar import features
from afar.agents.player import Player
from afar.album import Album
from afar.config import AfarConfig
from afar.intent import Intent
from afar.log import JsonlLedger
from afar.perception import ear
from afar.perception.album_context import Ears, HeardAlbum, build_album_context
from afar.perception.context import (
    CONDITIONS,
    RoundEntry,
    RunView,
    build_context,
    hears_others,
)
from afar.perception.embedder import AudioEmbedder

_SEQUENTIAL_CONDITIONS = ("isolation", "solo")
SPACES: tuple[str, ...] = ("audio", "intent")


class SetAborted(RuntimeError):
    """Raised when `after_round` asked run_set to stop before the last round.

    The rounds already played stay in the log as history (rule 3), but no
    features are computed and no release record is written — an aborted set
    never finished, and a record for it would be a lie. The conductor's
    SIGTERM path is the only caller: finish the current round, checkpoint,
    exit 0; the set replays whole on the next boot.
    """


@dataclass(frozen=True)
class SetResult:
    """What one set produced: the release record, and where its facts live.

    `release_record` is the content-addressed interaction record (also logged
    as a releases row); `paths` points at the run directory and the record's
    JSON file on disk.
    """

    release_record: dict[str, Any]
    paths: dict[str, Path]


def compute_space_features(
    embs: Mapping[str, Sequence[Sequence[float]]],
    *,
    rounds: int,
    ledger: JsonlLedger,
    space: str,
    stamps: Mapping[str, Any],
    row_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute and log one space's interaction features; return the block.

    The single feature-assembly path: `run_set` calls it for both spaces at the
    end of a set, and `scripts/reembed.py` calls it again for audio space when
    embeddings are recomputed with a real model. Every number is logged as a
    features row (stamped with `stamps` + `row_extra`, so a re-embed can mark
    its rows with the superseding model_id) and returned as
    {"influence", "convergence", "novelty", "asymmetry"} in exactly the shape
    the release record carries per space.
    """
    ids = list(embs)
    extra = dict(row_extra or {})
    graphs: dict[str, dict[str, float]] = {}
    asym: dict[str, dict[str, float]] = {}
    for t in range(1, rounds):
        graph = features.influence_graph(embs, t)
        edges = {f"{a}<-{b}": value for (a, b), value in graph.items()}
        graphs[str(t)] = edges
        ledger.write(
            "features",
            {**stamps, **extra, "space": space, "feature": "influence", "round": t, "edges": edges},
        )
        pairs: dict[str, float] = {}
        for a, b in combinations(ids, 2):
            value = features.asymmetry(graph[(a, b)], graph[(b, a)])
            pairs[f"{a}|{b}"] = value
            ledger.write(
                "features",
                {
                    **stamps,
                    **extra,
                    "space": space,
                    "feature": "asymmetry",
                    "round": t,
                    "pair": f"{a}|{b}",
                    "value": value,
                },
            )
        asym[str(t)] = pairs
    curve = features.convergence_curve(embs)
    for t, value in enumerate(curve):
        ledger.write(
            "features",
            {**stamps, **extra, "space": space, "feature": "convergence", "round": t, "value": value},
        )
    novelty_by: dict[str, dict[str, float]] = {pid: {} for pid in ids}
    for pid in ids:
        for t in range(1, rounds):
            value = features.novelty(embs[pid][t], embs[pid][:t])
            novelty_by[pid][str(t)] = value
            ledger.write(
                "features",
                {
                    **stamps,
                    **extra,
                    "space": space,
                    "feature": "novelty",
                    "round": t,
                    "player": pid,
                    "value": value,
                },
            )
    return {
        "influence": graphs,
        "convergence": curve,
        "novelty": novelty_by,
        "asymmetry": asym,
    }


def player_seed(seed: int, player_id: str, t: int) -> int:
    """Derive the render seed for one (player, round) from the set seed.

    Hash-offset rather than enumerated (seed + t * 3 + index) so seeds do not
    collide when rounds or players are added, and so a given (player, round)
    keeps its seed even if the roster order changes. Deterministic across
    processes — reproducibility of a whole set hangs on this.
    """
    offset = int(hashlib.sha256(f"{player_id}:{t}".encode("utf-8")).hexdigest()[:8], 16)
    return seed + offset


def track_seed(seed: int, artist_id: str, album_id: str, index: int) -> int:
    """Derive one track's render seed from the album's seed.

    Same hash-offset shape as `player_seed`, with the album's content hash in
    the key: a given (artist, album, track) always renders from the same seed,
    so a record replays byte-identically — and two different albums by the
    same artist under the same conductor seed cannot collide into the same
    audio.
    """
    key = f"{artist_id}:{album_id}:{index}".encode("utf-8")
    return seed + int(hashlib.sha256(key).hexdigest()[:8], 16)


# --- the album: the live piece's orchestrator ---------------------------------


@dataclass(frozen=True)
class RenderedTrack:
    """One finished song: what the artist decided, and what it became."""

    index: int
    title: str
    note: str
    intent: Intent
    intent_id: str
    audio_path: Path
    content_hash: str
    seed: int
    duration_s: int

    @property
    def lyrics(self) -> str:
        return self.intent.lyrics


@dataclass(frozen=True)
class AlbumResult:
    """One finished record, and everything a publisher needs to ship it.

    `album` is what the artist wrote (title, description, per-track words and
    DNA); `tracks` pairs each song with the audio it became; `record` is the
    content-addressed album record — the same double-duty shape `run_set`'s
    release record has: logged as an `albums` row, written to disk beside the
    run, and the thing the conductor's publish path reads. Nothing in it is
    staff-written, because nothing staff-written exists yet: the reactions
    happen after this returns.
    """

    album: Album
    album_id: str  # the album's content hash: what the artist decided
    artist_id: str
    tracks: tuple[RenderedTrack, ...]
    #: space -> {"influence": {album_id: float}, "convergence": float, "novelty": float}
    features: dict[str, dict[str, Any]]
    record: dict[str, Any]
    paths: dict[str, Path]

    @property
    def duration_s(self) -> int:
        return sum(t.duration_s for t in self.tracks)


def measure_heard_albums(
    albums: Sequence[HeardAlbum], ears: Ears
) -> tuple[HeardAlbum, ...]:
    """Attach the measured ear facts to the tracks this artist actually heard.

    `afar.perception.ear`, at album cadence: DSP runs ONCE per track (a failed
    measurement degrades that track to the embedding relations — it never
    blocks a record), and the loudness/brightness terciles are taken against
    THIS listening pass's pool, because "quiet" is only meaningful as a
    comparison and the honest comparison is the other records that reached
    this artist at the same time.

    A track with no logged audio vector was not heard — it keeps no `heard`
    dict at all, rather than a dict of Nones that would read as "I heard it
    and it had no qualities".
    """
    audio_vecs = ears.space("audio")
    if not audio_vecs:
        return tuple(albums)
    dsp_by: dict[str, Optional[dict[str, float]]] = {}
    rms_pool: list[float] = []
    centroid_pool: list[float] = []
    for album in albums:
        for track in album.tracks:
            digest = track.content_hash
            if not digest or digest in dsp_by or digest not in audio_vecs:
                continue
            path = ears.audio.get(digest)
            facts = ear.dsp_facts(path) if path is not None else None
            dsp_by[digest] = facts
            if facts is not None:
                rms_pool.append(facts["rms"])
                centroid_pool.append(facts["centroid_hz"])

    your_vec = ears.own_last("audio")
    your_prev_vec = ears.own_before_last("audio")
    maker_past = ears.maker_past.get("audio", {})
    measured: list[HeardAlbum] = []
    for album in albums:
        heard_by_hash: dict[str, dict[str, Any]] = {}
        for track in album.tracks:
            digest = track.content_hash
            if digest not in dsp_by:
                continue
            heard_by_hash[digest] = ear.hear(
                ears.audio.get(digest) or Path(""),
                audio_vecs[digest],
                {
                    "your_vec": your_vec,
                    "your_prev_vec": your_prev_vec,
                    "their_prev_vec": maker_past.get(album.artist_id),
                    "rms_pool": list(rms_pool),
                    "centroid_pool": list(centroid_pool),
                    "dsp": dsp_by[digest],
                },
            )
        measured.append(album.with_heard(heard_by_hash) if heard_by_hash else album)
    return tuple(measured)


def run_album(
    player: Player,
    *,
    n_tracks: int,
    duration_s: int,
    config: AfarConfig,
    ledger: JsonlLedger,
    embedder: AudioEmbedder,
    seed: int,
    heard: Sequence[HeardAlbum] = (),
    own_last: Optional[HeardAlbum] = None,
    ears: Optional[Ears] = None,
    isolated: bool = False,
) -> AlbumResult:
    """One artist, one record, start to finish. See the module docstring.

    `heard` is the other artists' recent records this one gets to hear and
    `own_last` is its own previous record — both as sleeves; `ears` is the
    runner-side measurement material (audio files and logged vectors, keyed by
    artifact hash) which never enters the prompt as anything but measured
    facts. `isolated=True` is the experiment's control: the artist hears no
    one.

    Everything is logged before this returns: the perceptions row carries the
    context verbatim (what the artist saw, not a paraphrase), one intents +
    artifacts + two embeddings rows per track, the album-cadence features in
    both spaces, and the album record itself.
    """
    artist_id = player.persona.metadata["player_id"]
    ears = ears or Ears()
    heard = measure_heard_albums(tuple(heard), ears) if not isolated else tuple(heard)
    context = build_album_context(
        artist_id, heard=heard, own_last=own_last, isolated=isolated
    )

    ledger.write(
        "runs",
        {
            "id": ledger.run_id,
            "kind": "album",
            "artist": artist_id,
            "n_tracks": n_tracks,
            "duration_s": duration_s,
            "seed": seed,
            "isolated": isolated,
            "heard": [a.album_id or a.title for a in heard],
            "live": config.live,
            "renderer": config.renderer.name,
            "embedder": embedder.name,
        },
    )

    album = player.write_album(context, n_tracks=n_tracks, duration_s=duration_s)
    album_id = album.content_hash()
    album_stamps = {"seed": seed, "album": album_id, "player": artist_id}
    ledger.write("perceptions", {**album_stamps, "context": context})

    tracks: list[RenderedTrack] = []
    vectors: dict[str, list[list[float]]] = {space: [] for space in SPACES}
    for index, track in enumerate(album.tracks):
        player.seed = track_seed(seed, artist_id, album_id, index)
        player.duration_s = duration_s
        artifact = player.execute(Decision(data={"intent": track.intent}))
        content_hash = artifact.metadata["content_hash"]
        intent_id = track.intent.content_hash()
        stamps = {
            **album_stamps,
            "seed": player.seed,
            "track": index,
            "renderer_version": artifact.metadata["renderer_version"],
            "prompt_sha": artifact.metadata["prompt_sha"],
        }
        ledger.write(
            "intents",
            {
                **stamps,
                "id": intent_id,
                "title": track.title,
                "intent": track.intent.to_dna_dict(),
                "line": track.note,
                "lyrics": track.intent.lyrics,
                "rationale": track.intent.rationale,
            },
        )
        ledger.write(
            "artifacts",
            {
                **stamps,
                "id": content_hash,
                "kind": artifact.kind,
                "title": track.title,
                "path": artifact.body,
                "hash": content_hash,
                "intent_id": intent_id,
            },
        )
        audio_vec = embedder.embed(Path(artifact.body))
        intent_vec = features.intent_vector(track.intent)
        ledger.write(
            "embeddings",
            {
                **stamps,
                "space": "audio",
                "model_id": embedder.name,
                "dim": embedder.dim,
                "artifact_id": content_hash,
                "vector": audio_vec,
            },
        )
        ledger.write(
            "embeddings",
            {
                **stamps,
                "space": "intent",
                "model_id": "intent-vector",
                "dim": len(intent_vec),
                "intent_vector_version": features.INTENT_VECTOR_VERSION,
                "intent_id": intent_id,
                "vector": intent_vec,
            },
        )
        vectors["audio"].append(audio_vec)
        vectors["intent"].append(intent_vec)
        tracks.append(
            RenderedTrack(
                index=index,
                title=track.title,
                note=track.note,
                intent=track.intent,
                intent_id=intent_id,
                audio_path=Path(artifact.body),
                content_hash=content_hash,
                seed=player.seed,
                duration_s=duration_s,
            )
        )

    feature_block = _album_features(
        album_id, artist_id, heard, ears, vectors, ledger=ledger, stamps=album_stamps
    )

    # The record is a pure function of (artist, album, seed, adapters, ears):
    # no run_id, timestamps or filesystem paths, so an identical record hashes
    # identically — that stability is the proof the whole album is
    # reproducible from its inputs.
    record_body: dict[str, Any] = {
        "album_id": album_id,
        "artist_id": artist_id,
        "album": album.to_row(),
        "session": {
            "n_tracks": n_tracks,
            "duration_s": duration_s,
            "seed": seed,
            "isolated": isolated,
            "embedder": {"name": embedder.name, "dim": embedder.dim},
            "intent_vector_version": features.INTENT_VECTOR_VERSION,
        },
        "heard": [
            {"album_id": a.album_id, "artist_id": a.artist_id, "title": a.title}
            for a in heard
        ],
        "tracks": [
            {
                "index": t.index,
                "title": t.title,
                "note": t.note,
                "lyrics": t.lyrics,
                "hash": t.content_hash,
                "intent_id": t.intent_id,
                "seed": t.seed,
                "duration_s": t.duration_s,
            }
            for t in tracks
        ],
        "features": feature_block,
    }
    canonical = json.dumps(record_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    record = {"record_id": record_id, **record_body}
    ledger.write("albums", {**album_stamps, "id": album_id, "record": record})
    record_path = ledger.run_dir / f"album-{album_id[:12]}.json"
    record_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return AlbumResult(
        album=album,
        album_id=album_id,
        artist_id=artist_id,
        tracks=tuple(tracks),
        features=feature_block,
        record=record,
        paths={"run_dir": ledger.run_dir, "record": record_path},
    )


def _album_features(
    album_id: str,
    artist_id: str,
    heard: Sequence[HeardAlbum],
    ears: Ears,
    vectors: Mapping[str, Sequence[Sequence[float]]],
    *,
    ledger: JsonlLedger,
    stamps: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compute and log the album-cadence features in BOTH spaces.

    The heard albums' own positions are the centroids of the vectors the log
    already holds for their tracks (`ears.vectors`), so influence between two
    records is computed from exactly the coordinates both records were logged
    at — the same no-drift discipline `_hear_round` keeps per round. An album
    with no logged vectors simply is not an edge: it was on the sleeve, but
    nothing measurable of it reached here.
    """
    block: dict[str, dict[str, Any]] = {}
    for space in SPACES:
        space_vecs = ears.space(space)
        heard_vecs: dict[str, Sequence[float]] = {}
        for album in heard:
            track_vecs = [
                space_vecs[t.content_hash]
                for t in album.tracks
                if t.content_hash in space_vecs
            ]
            if track_vecs:
                heard_vecs[album.album_id or album.title] = features.album_vector(track_vecs)
        mine = features.album_vector(vectors[space])
        computed = features.album_features(
            mine, heard=heard_vecs, own_past=ears.own_past.get(space, ())
        )
        block[space] = computed
        for heard_id, value in computed["influence"].items():
            ledger.write(
                "features",
                {
                    **stamps,
                    "space": space,
                    "feature": "influence",
                    "cadence": "album",
                    "from_album": heard_id,
                    "value": value,
                },
            )
        for name in ("convergence", "novelty"):
            ledger.write(
                "features",
                {
                    **stamps,
                    "space": space,
                    "feature": name,
                    "cadence": "album",
                    "value": computed[name],
                },
            )
    return block


# --- the set: the offline experiment's orchestrator ---------------------------


def _hear_round(
    entries: Mapping[str, RoundEntry],
    audio_paths: Mapping[str, Path],
    audio_vecs: Mapping[str, Sequence[Sequence[float]]],
    t: int,
    rms_pool: list[float],
    centroid_pool: list[float],
) -> dict[str, RoundEntry]:
    """Measure this round's takes for next round's ears (contact sets only).

    DSP runs ONCE per take (`ear.dsp_facts`; both listeners share the result,
    and a failed measurement degrades that take to the embedding relations —
    it never blocks the round). The pools are extended BEFORE bucketing so
    "quiet"/"dark" mean quiet/dark vs. the whole set so far, this round
    included. Then one `ear.hear` per (take, listener) — the relations use
    EXACTLY the audio vectors this round just logged, so what the acts are
    told they heard and what features.py later computes cannot drift apart.
    Returns the entries re-made with `heard_by` attached; `build_context`
    decides who receives it.
    """
    ids = list(entries)
    dsp_by: dict[str, Optional[dict[str, float]]] = {}
    for pid in ids:
        facts = ear.dsp_facts(audio_paths[pid])
        dsp_by[pid] = facts
        if facts is not None:
            rms_pool.append(facts["rms"])
            centroid_pool.append(facts["centroid_hz"])
    heard_entries: dict[str, RoundEntry] = {}
    for pid in ids:
        listeners: dict[str, dict[str, Any]] = {}
        for listener in ids:
            if listener == pid:
                continue
            listeners[listener] = ear.hear(
                audio_paths[pid],
                audio_vecs[pid][t],
                {
                    "your_vec": audio_vecs[listener][t],
                    "your_prev_vec": audio_vecs[listener][t - 1] if t >= 1 else None,
                    "their_prev_vec": audio_vecs[pid][t - 1] if t >= 1 else None,
                    "rms_pool": list(rms_pool),
                    "centroid_pool": list(centroid_pool),
                    "dsp": dsp_by[pid],
                },
            )
        heard_entries[pid] = replace(entries[pid], heard_by=listeners)
    return heard_entries


def _play(
    player: Player, context: Mapping[str, Any], seed: int, duration_s: int
) -> dict[str, Any]:
    """One player's full PDE loop for one round. No logging here: this runs on
    a worker thread under fan_out, and the ledger is orchestrator-only."""
    perception = player.perceive(context)
    decision = player.decide(perception)
    player.seed = seed
    player.duration_s = duration_s
    artifact = player.execute(decision)
    return {"intent": decision.data["intent"], "artifact": artifact}


def run_set(
    players: list[Player],
    *,
    rounds: int,
    condition: str,
    config: AfarConfig,
    ledger: JsonlLedger,
    embedder: AudioEmbedder,
    seed: int,
    after_round: Optional[Callable[[int], bool]] = None,
    direction: Optional[Mapping[str, Any]] = None,
) -> SetResult:
    """Play one set and return its interaction record. See module docstring.

    `after_round(t)` — the conductor's seam — is called on the orchestrator
    thread after round `t` is fully logged (its generation spend can be
    counted there). Returning True asks the set to stop: before the last
    round that raises SetAborted (the SIGTERM finish-current-round contract);
    on the last round the set simply completes.

    `direction` is the Producer's set-start direction (the seam rule 2 leaves
    open): it rides into every round's context as frame — never as peer
    material — via `build_context`, and its `duration_s` (default 30) is the
    whole set's take length. None means an undirected set (cold start, or a
    pre-conductor caller): identical to the pre-direction behavior.
    """
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; expected one of {CONDITIONS}")
    ids = [p.persona.metadata["player_id"] for p in players]
    by_id = dict(zip(ids, players))
    duration_s = int(direction.get("duration_s", 30)) if direction else 30

    set_stamps = {"condition": condition, "seed": seed}
    ledger.write(
        "runs",
        {
            **set_stamps,
            "id": ledger.run_id,
            "kind": "set",
            "players": ids,
            "rounds": rounds,
            "duration_s": duration_s,
            "directed": direction is not None,
            "live": config.live,
            "renderer": config.renderer.name,
            "embedder": embedder.name,
        },
    )
    ledger.write(
        "sets",
        {**set_stamps, "id": f"set-{condition}-{seed}", "players": ids, "rounds": rounds},
    )

    view = RunView()
    vectors: dict[str, dict[str, list[list[float]]]] = {
        space: {pid: [] for pid in ids} for space in SPACES
    }
    round_frames: list[dict[str, dict[str, str]]] = []  # per round: pid -> line/lyrics/rationale
    round_hashes: list[dict[str, str]] = []  # per round: pid -> artifact content hash
    # Measured hearing (contact sets): the set-so-far DSP pools the loudness/
    # brightness terciles compare against — one value per measurable take.
    rms_pool: list[float] = []
    centroid_pool: list[float] = []

    for t in range(rounds):
        contexts = {
            pid: build_context(pid, t, view, condition, direction=direction) for pid in ids
        }
        seeds = {pid: player_seed(seed, pid, t) for pid in ids}
        stages = [
            Stage(
                name=pid,
                fn=lambda _ctx, p=by_id[pid], c=contexts[pid], s=seeds[pid]: _play(
                    p, c, s, duration_s
                ),
            )
            for pid in ids
        ]
        if condition in _SEQUENTIAL_CONDITIONS:
            results = {stage.name: stage.run({}) for stage in stages}
        else:
            results = fan_out(stages, {})

        entries: dict[str, RoundEntry] = {}
        frames: dict[str, dict[str, str]] = {}
        hashes: dict[str, str] = {}
        for pid in ids:
            intent: Intent = results[pid]["intent"]
            artifact: Artifact = results[pid]["artifact"]
            content_hash = artifact.metadata["content_hash"]
            intent_id = intent.content_hash()
            stamps = {
                "condition": condition,
                "seed": seeds[pid],
                "renderer_version": artifact.metadata["renderer_version"],
                "prompt_sha": artifact.metadata["prompt_sha"],
            }
            # The logged context IS the perceive input, verbatim — rule 1's
            # audit trail. Same row shapes as Step A's render_one, plus round.
            ledger.write(
                "perceptions",
                {**stamps, "round": t, "player": pid, "context": contexts[pid]},
            )
            ledger.write(
                "intents",
                {
                    **stamps,
                    "round": t,
                    "id": intent_id,
                    "player": pid,
                    "intent": intent.to_dna_dict(),
                    "line": intent.line,
                    "lyrics": intent.lyrics,
                    "rationale": intent.rationale,
                },
            )
            ledger.write(
                "artifacts",
                {
                    **stamps,
                    "round": t,
                    "id": content_hash,
                    "kind": artifact.kind,
                    "player": pid,
                    "path": artifact.body,
                    "hash": content_hash,
                    "intent_id": intent_id,
                },
            )

            audio_vec = embedder.embed(Path(artifact.body))
            intent_vec = features.intent_vector(intent)
            ledger.write(
                "embeddings",
                {
                    **stamps,
                    "round": t,
                    "player": pid,
                    "space": "audio",
                    "model_id": embedder.name,
                    "dim": embedder.dim,
                    "artifact_id": content_hash,
                    "vector": audio_vec,
                },
            )
            ledger.write(
                "embeddings",
                {
                    **stamps,
                    "round": t,
                    "player": pid,
                    "space": "intent",
                    "model_id": "intent-vector",
                    "dim": len(intent_vec),
                    "intent_vector_version": features.INTENT_VECTOR_VERSION,
                    "intent_id": intent_id,
                    "vector": intent_vec,
                },
            )
            vectors["audio"][pid].append(audio_vec)
            vectors["intent"][pid].append(intent_vec)
            entries[pid] = RoundEntry(
                player_id=pid,
                line=intent.line,
                intent=intent.to_dna_dict(),
                content_hash=content_hash,
            )
            frames[pid] = {"line": intent.line, "lyrics": intent.lyrics, "rationale": intent.rationale}
            hashes[pid] = content_hash
            player = by_id[pid]
            player.memory.remember({"persona": player.persona.name, "artifact_kind": artifact.kind})

        if hears_others(condition):
            # Measure what this round's takes SOUNDED like while the audio is
            # at hand — next round's build_context hands each listener their
            # heard dict. Alone conditions skip the measurement entirely: no
            # one would ever receive it.
            audio_paths = {pid: Path(results[pid]["artifact"].body) for pid in ids}
            entries = _hear_round(
                entries, audio_paths, vectors["audio"], t, rms_pool, centroid_pool
            )
        view.append_round(entries)
        round_frames.append(frames)
        round_hashes.append(hashes)
        ledger.write(
            "rounds",
            {**set_stamps, "round": t, "players": ids, "artifacts": [hashes[pid] for pid in ids]},
        )
        if after_round is not None and after_round(t) and t < rounds - 1:
            raise SetAborted(f"set stopped after round {t} of {rounds}")

    # --- features, both spaces, logged and collected for the record ----------
    feature_block: dict[str, dict[str, Any]] = {
        "influence": {},
        "convergence": {},
        "novelty": {},
        "asymmetry": {},
    }
    for space in SPACES:
        block = compute_space_features(
            vectors[space],
            rounds=rounds,
            ledger=ledger,
            space=space,
            stamps=set_stamps,
        )
        for feature_name, value in block.items():
            feature_block[feature_name][space] = value

    # --- the release record ---------------------------------------------------
    # Everything in the record is a pure function of (personas, condition,
    # rounds, seed, adapters): no run_id, timestamps, or filesystem paths, so
    # two identical runs hash identically — that stability is the test that
    # the whole set is reproducible from its inputs.
    record_body: dict[str, Any] = {
        "set": {
            "condition": condition,
            "rounds": rounds,
            "players": ids,
            "seed": seed,
            "duration_s": duration_s,
            "embedder": {"name": embedder.name, "dim": embedder.dim},
            "intent_vector_version": features.INTENT_VECTOR_VERSION,
        },
        "influence": feature_block["influence"],
        "convergence": feature_block["convergence"],
        "novelty": feature_block["novelty"],
        "asymmetry": feature_block["asymmetry"],
        "rounds": round_frames,
        "artifacts": round_hashes,
    }
    canonical = json.dumps(record_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    release_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    release_record = {"release_id": release_id, **record_body}
    ledger.write("releases", {**set_stamps, "id": release_id, "record": release_record})
    release_path = ledger.run_dir / f"release-{release_id[:12]}.json"
    release_path.write_text(
        json.dumps(release_record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return SetResult(
        release_record=release_record,
        paths={"run_dir": ledger.run_dir, "release": release_path},
    )
