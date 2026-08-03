"""Interaction features: is influence moving between the players, and which way?

The cluster/centroid/drift math is ported from moldzine's Phase 0 bench
(`mold/perception/bench.py`) — `_cosine`, `_centroid`, `cluster`, and
`week_drift` renamed `round_drift` (AFAR's unit of time is the round). On top
of that sit the cross-perception features the experiment actually claims
things with: influence, convergence, novelty, asymmetry.

Every feature takes plain vectors the CALLER supplies, so each one computes
identically over either space — audio space (AudioEmbedder vectors of the
rendered tracks) or intent space (`intent_vector` of the logged DNA). The
experiment needs both: if the two spaces disagree, the renderer is doing the
influencing, not the players.

Pure Python on purpose: three players and a handful of rounds need no numpy,
and stdlib math keeps every number reproducible from the log alone.
"""

from __future__ import annotations

import hashlib
import math
from itertools import combinations
from typing import Any, Mapping, Sequence

from afar.intent import SONIC_AXES, VOCAL_AXES, Intent

# Bump on ANY change to the intent_vector recipe: logged vectors from
# different recipes must never be compared, and the version column in the
# embeddings table is what enforces that at analysis time.
INTENT_VECTOR_VERSION = "1"
GENRE_BUCKETS = 8


# --- math ported from mold's bench -------------------------------------------


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def _centroid(vectors: list[Sequence[float]]) -> list[float]:
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


def cluster(embedded: list[dict[str, Any]], threshold: float) -> list[list[dict[str, Any]]]:
    """Greedy leader clustering by cosine similarity. Order-stable, dead simple.

    Right-sized for a few dozen clips (the persona gate); a production
    clusterer replaces this without touching anything downstream. Items are
    dicts carrying at least a "vector" key; they come back grouped, densest
    cluster first.
    """
    clusters: list[dict[str, Any]] = []  # {"centroid": [...], "members": [...]}
    for item in embedded:
        best, best_sim = None, threshold
        for c in clusters:
            sim = _cosine(item["vector"], c["centroid"])
            if sim >= best_sim:
                best, best_sim = c, sim
        if best is None:
            clusters.append({"centroid": list(item["vector"]), "members": [item]})
        else:
            best["members"].append(item)
            best["centroid"] = _centroid([m["vector"] for m in best["members"]])
    clusters.sort(key=lambda c: len(c["members"]), reverse=True)
    return [c["members"] for c in clusters]


def round_drift(embedded: list[dict[str, Any]]) -> list[tuple[Any, Any, float]]:
    """Cosine distance between consecutive rounds' centroids — literal drift.

    mold's `week_drift` with the grouping key renamed: items carry a "round"
    key instead of "week". Same math, same (prev, cur, distance) triples.
    """
    rounds: dict[Any, list[Sequence[float]]] = {}
    for item in embedded:
        rounds.setdefault(item["round"], []).append(item["vector"])
    ordered = sorted(rounds)
    out = []
    for prev, cur in zip(ordered, ordered[1:]):
        d = 1.0 - _cosine(_centroid(rounds[prev]), _centroid(rounds[cur]))
        out.append((prev, cur, d))
    return out


# --- the cross-perception features -------------------------------------------


def influence(
    e_a_t: Sequence[float], e_b_prev: Sequence[float], e_a_prev: Sequence[float]
) -> float:
    """How much A's new material moved toward B's last statement vs. its own.

    I(a<-b, t) = cos(e_a_t, e_b_prev) - cos(e_a_t, e_a_prev). Zero-centred so
    the SIGN carries the finding: positive means A now sounds more like what B
    just played than like A's own previous round (B pulled A); negative means
    A stayed home.
    """
    return _cosine(e_a_t, e_b_prev) - _cosine(e_a_t, e_a_prev)


def convergence(vectors_at_t: Sequence[Sequence[float]]) -> float:
    """Mean pairwise cosine among the players' round-t vectors.

    1.0 means the band has collapsed into one voice. Fewer than two vectors
    have no pairs to disagree, so that degenerate case reads as 1.0 rather
    than raising — a one-player "band" is trivially converged.
    """
    pairs = list(combinations(vectors_at_t, 2))
    if not pairs:
        return 1.0
    return sum(_cosine(a, b) for a, b in pairs) / len(pairs)


def novelty(e_a_t: Sequence[float], own_past_vectors: Sequence[Sequence[float]]) -> float:
    """1 - cos(now, centroid(own past)): how far a player left its own history.

    A literal repeat scores 0. With no history yet there is nothing to depart
    from, so the score is 0.0 by definition rather than an error.
    """
    if not own_past_vectors:
        return 0.0
    return 1.0 - _cosine(e_a_t, _centroid(list(own_past_vectors)))


def asymmetry(i_ab: float, i_ba: float) -> float:
    """I(a<-b) - I(b<-a): who is leading. Positive means b moves a more than
    a moves b — influence between this pair flows b -> a."""
    return i_ab - i_ba


def influence_graph(
    embeddings_by_player: Mapping[str, Sequence[Sequence[float]]], t: int
) -> dict[tuple[str, str], float]:
    """The full directed influence graph at round t: {(a, b): I(a<-b, t)}.

    Both orders for every pair — the graph is directed, and the asymmetry
    between the two directions is itself a finding. `embeddings_by_player`
    maps player id -> per-round vectors (index = round). Needs a previous
    round to compare against, so t must be >= 1.
    """
    if t < 1:
        raise ValueError("influence needs a previous round to compare against (t >= 1)")
    graph: dict[tuple[str, str], float] = {}
    for a in embeddings_by_player:
        for b in embeddings_by_player:
            if a == b:
                continue
            graph[(a, b)] = influence(
                embeddings_by_player[a][t],
                embeddings_by_player[b][t - 1],
                embeddings_by_player[a][t - 1],
            )
    return graph


def convergence_curve(
    embeddings_by_player: Mapping[str, Sequence[Sequence[float]]]
) -> list[float]:
    """Convergence at every round: one number per round, in round order.

    Truncates to the shortest player history so a half-finished set still
    yields a curve over the rounds everyone completed.
    """
    if not embeddings_by_player:
        return []
    rounds = min(len(vectors) for vectors in embeddings_by_player.values())
    return [
        convergence([embeddings_by_player[pid][t] for pid in embeddings_by_player])
        for t in range(rounds)
    ]


# --- album cadence ------------------------------------------------------------
# The album is the unit of work now (docs/SPEC.md), so the same four features
# are computed between a NEW ALBUM and the albums that artist heard, at album
# cadence instead of round cadence. The math is unchanged and deliberately so:
# an album is represented by the centroid of its tracks' vectors, and then it
# is just another point — influence, convergence and novelty read exactly as
# they did per round, which is what lets the round-based history and the
# album-based history be plotted on one axis.


def album_vector(track_vectors: Sequence[Sequence[float]]) -> list[float]:
    """One album's position in a space: the centroid of its tracks' vectors.

    Works in either space — MERT vectors of the rendered tracks, or
    `intent_vector` of each track's DNA. Raises on an empty album: a record
    with no tracks has no position, and silently returning a zero vector would
    put it at the origin, equidistant from everything.
    """
    vectors = [list(v) for v in track_vectors]
    if not vectors:
        raise ValueError("an album vector needs at least one track vector")
    return _centroid(vectors)


def album_features(
    album_vec: Sequence[float],
    *,
    heard: Mapping[str, Sequence[float]],
    own_past: Sequence[Sequence[float]] = (),
) -> dict[str, Any]:
    """The album-cadence feature block for one new record, in one space.

    - influence: I(new <- heard_b) for every album heard, keyed by that
      album's id. Needs the artist's own previous album to compare against
      (the zero-centring is "closer to them than to my own last record"), so a
      debut — nothing in `own_past` — yields an empty influence map rather
      than a number that would mean nothing.
    - convergence: mean pairwise cosine over the new album and everything it
      heard. 1.0 means this corner of the world has collapsed into one voice.
      With nothing heard there are no pairs, so it reads 1.0 by the same
      convention `convergence` already uses.
    - novelty: how far the new record left the artist's own history. 0.0 for a
      debut, by definition — there is nothing yet to depart from.

    `own_past` is the artist's previous albums as album vectors, oldest first.
    Pure: the caller supplies every vector, so this computes identically over
    either space and is reproducible from the log alone.
    """
    influences: dict[str, float] = {}
    own_prev = own_past[-1] if own_past else None
    if own_prev is not None:
        for album_id, heard_vec in heard.items():
            influences[album_id] = influence(album_vec, heard_vec, own_prev)
    return {
        "influence": influences,
        "convergence": convergence([album_vec, *heard.values()]),
        "novelty": novelty(album_vec, list(own_past)),
    }


# --- intent space -------------------------------------------------------------


def intent_vector(intent: Intent) -> list[float]:
    """A deterministic 18-dim vector of the DNA — the intent-space twin of an
    audio embedding, computable with no audio and no model.

    Layout (pinned; bump INTENT_VECTOR_VERSION on ANY change):
      [0]      era / 10                          (0..1)
      [1:8]    the 7 sonicPalette axes, schema order
      [8:10]   the 2 vocalCharacter axes, schema order
      [10:18]  8 genre buckets: each influence's weight summed into bucket
               sha256(genre.lower()) % 8 — a hashed bag-of-genres, so unseen
               genres need no vocabulary and the dimension never grows.

    Hash-bucketing collides on purpose (8 buckets, open genre vocabulary);
    that is acceptable noise for a 4-influence DNA, and determinism across
    processes matters more than resolution here.
    """
    vec: list[float] = [intent.era / 10.0]
    vec.extend(getattr(intent.sonicPalette, axis) for axis in SONIC_AXES)
    vec.extend(getattr(intent.vocalCharacter, axis) for axis in VOCAL_AXES)
    buckets = [0.0] * GENRE_BUCKETS
    for inf in intent.influences:
        digest = hashlib.sha256(inf.genre.lower().encode("utf-8")).hexdigest()
        buckets[int(digest, 16) % GENRE_BUCKETS] += inf.weight
    return vec + buckets
