"""run_set: three players, N rounds, cross-perception, one interaction record.

The Step B orchestrator — the first thing that is actually the piece. Each
round it builds every player's context (`build_context`, the single condition
chokepoint), runs all three PERCEIVE -> DECIDE -> EXECUTE loops, embeds every
rendered track in BOTH spaces (audio via the injected AudioEmbedder, intent
via `features.intent_vector`), and logs perceptions / intents / artifacts /
embeddings as first-class rows. After the last round it computes the
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
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping

from ensemble.agent import Artifact
from ensemble.pipeline import Stage, fan_out

from afar import features
from afar.agents.player import Player
from afar.config import AfarConfig
from afar.intent import Intent
from afar.log import JsonlLedger
from afar.perception.context import CONDITIONS, RoundEntry, RunView, build_context
from afar.perception.embedder import AudioEmbedder

_SEQUENTIAL_CONDITIONS = ("isolation", "solo")
SPACES: tuple[str, ...] = ("audio", "intent")


@dataclass(frozen=True)
class SetResult:
    """What one set produced: the release record, and where its facts live.

    `release_record` is the content-addressed interaction record (also logged
    as a releases row); `paths` points at the run directory and the record's
    JSON file on disk.
    """

    release_record: dict[str, Any]
    paths: dict[str, Path]


def player_seed(seed: int, player_id: str, t: int) -> int:
    """Derive the render seed for one (player, round) from the set seed.

    Hash-offset rather than enumerated (seed + t * 3 + index) so seeds do not
    collide when rounds or players are added, and so a given (player, round)
    keeps its seed even if the roster order changes. Deterministic across
    processes — reproducibility of a whole set hangs on this.
    """
    offset = int(hashlib.sha256(f"{player_id}:{t}".encode("utf-8")).hexdigest()[:8], 16)
    return seed + offset


def _play(player: Player, context: Mapping[str, Any], seed: int) -> dict[str, Any]:
    """One player's full PDE loop for one round. No logging here: this runs on
    a worker thread under fan_out, and the ledger is orchestrator-only."""
    perception = player.perceive(context)
    decision = player.decide(perception)
    player.seed = seed
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
) -> SetResult:
    """Play one set and return its interaction record. See module docstring."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; expected one of {CONDITIONS}")
    ids = [p.persona.metadata["player_id"] for p in players]
    by_id = dict(zip(ids, players))

    set_stamps = {"condition": condition, "seed": seed}
    ledger.write(
        "runs",
        {
            **set_stamps,
            "id": ledger.run_id,
            "kind": "set",
            "players": ids,
            "rounds": rounds,
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
    round_frames: list[dict[str, dict[str, str]]] = []  # per round: pid -> line/rationale
    round_hashes: list[dict[str, str]] = []  # per round: pid -> artifact content hash

    for t in range(rounds):
        contexts = {pid: build_context(pid, t, view, condition) for pid in ids}
        seeds = {pid: player_seed(seed, pid, t) for pid in ids}
        stages = [
            Stage(name=pid, fn=lambda _ctx, p=by_id[pid], c=contexts[pid], s=seeds[pid]: _play(p, c, s))
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
            frames[pid] = {"line": intent.line, "rationale": intent.rationale}
            hashes[pid] = content_hash
            player = by_id[pid]
            player.memory.remember({"persona": player.persona.name, "artifact_kind": artifact.kind})

        view.append_round(entries)
        round_frames.append(frames)
        round_hashes.append(hashes)
        ledger.write(
            "rounds",
            {**set_stamps, "round": t, "players": ids, "artifacts": [hashes[pid] for pid in ids]},
        )

    # --- features, both spaces, logged and collected for the record ----------
    feature_block: dict[str, dict[str, Any]] = {
        "influence": {},
        "convergence": {},
        "novelty": {},
        "asymmetry": {},
    }
    for space in SPACES:
        embs = vectors[space]
        graphs: dict[str, dict[str, float]] = {}
        asym: dict[str, dict[str, float]] = {}
        for t in range(1, rounds):
            graph = features.influence_graph(embs, t)
            edges = {f"{a}<-{b}": value for (a, b), value in graph.items()}
            graphs[str(t)] = edges
            ledger.write(
                "features",
                {**set_stamps, "space": space, "feature": "influence", "round": t, "edges": edges},
            )
            pairs: dict[str, float] = {}
            for a, b in combinations(ids, 2):
                value = features.asymmetry(graph[(a, b)], graph[(b, a)])
                pairs[f"{a}|{b}"] = value
                ledger.write(
                    "features",
                    {
                        **set_stamps,
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
                {**set_stamps, "space": space, "feature": "convergence", "round": t, "value": value},
            )
        novelty_by: dict[str, dict[str, float]] = {pid: {} for pid in ids}
        for pid in ids:
            for t in range(1, rounds):
                value = features.novelty(embs[pid][t], embs[pid][:t])
                novelty_by[pid][str(t)] = value
                ledger.write(
                    "features",
                    {
                        **set_stamps,
                        "space": space,
                        "feature": "novelty",
                        "round": t,
                        "player": pid,
                        "value": value,
                    },
                )
        feature_block["influence"][space] = graphs
        feature_block["convergence"][space] = curve
        feature_block["novelty"][space] = novelty_by
        feature_block["asymmetry"][space] = asym

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
