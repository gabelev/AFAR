"""Feature math: signs, identities, and the pinned intent-vector recipe."""

import json

import pytest

from afar import features
from afar.config import _MOCK_INTENTS
from afar.intent import SONIC_AXES, VOCAL_AXES, Intent


def _intent(player_id: str = "silt") -> Intent:
    return Intent.from_json(json.dumps(_MOCK_INTENTS[player_id]))


def test_influence_sign_tracks_who_the_player_moved_toward():
    a_prev, b_prev = [1.0, 0.0], [0.0, 1.0]
    toward_b = [0.1, 1.0]  # near b's previous statement
    toward_self = [1.0, 0.1]  # stayed home
    assert features.influence(toward_b, b_prev, a_prev) > 0
    assert features.influence(toward_self, b_prev, a_prev) < 0


def test_convergence_of_identical_vectors_is_one():
    v = [0.3, 0.7, 0.1]
    assert features.convergence([v, v, v]) == pytest.approx(1.0)


def test_novelty_of_a_repeat_is_zero():
    v = [0.5, 0.5]
    assert features.novelty(v, [v, v]) == pytest.approx(0.0)


def test_influence_graph_is_directed():
    # a moved toward b's opening; b repeated itself. I(a<-b) must not mirror
    # I(b<-a) — the asymmetry between the two directions IS the finding.
    embs = {
        "a": [[1.0, 0.0], [0.2, 1.0]],
        "b": [[0.0, 1.0], [0.0, 1.0]],
    }
    graph = features.influence_graph(embs, 1)
    assert set(graph) == {("a", "b"), ("b", "a")}
    assert graph[("a", "b")] > 0
    assert graph[("b", "a")] < 0
    assert graph[("a", "b")] != graph[("b", "a")]


def test_influence_graph_needs_a_previous_round():
    with pytest.raises(ValueError):
        features.influence_graph({"a": [[1.0]], "b": [[1.0]]}, 0)


def test_asymmetry_is_the_signed_difference():
    assert features.asymmetry(0.4, 0.1) == pytest.approx(0.3)
    assert features.asymmetry(0.1, 0.4) == pytest.approx(-0.3)


def test_round_drift_matches_the_bench_math_on_a_hand_example():
    # Round 0 centroid [1, 0], round 1 centroid [0, 1]: cosine 0, drift 1.
    embedded = [
        {"round": 0, "vector": [1.0, 0.0]},
        {"round": 0, "vector": [1.0, 0.0]},
        {"round": 1, "vector": [0.0, 1.0]},
    ]
    ((prev, cur, drift),) = features.round_drift(embedded)
    assert (prev, cur) == (0, 1)
    assert drift == pytest.approx(1.0)


def test_convergence_curve_covers_every_round():
    v = [1.0, 0.0]
    embs = {"a": [v, v], "b": [v, [0.0, 1.0]]}
    curve = features.convergence_curve(embs)
    assert len(curve) == 2
    assert curve[0] == pytest.approx(1.0)
    assert curve[1] == pytest.approx(0.0)


def test_intent_vector_is_deterministic_and_version_pinned():
    assert features.INTENT_VECTOR_VERSION == "1"
    intent = _intent()
    vec = features.intent_vector(intent)
    assert vec == features.intent_vector(intent)  # pure function of the DNA
    assert len(vec) == 1 + len(SONIC_AXES) + len(VOCAL_AXES) + features.GENRE_BUCKETS
    assert vec[0] == pytest.approx(intent.era / 10)
    assert vec[1:8] == [getattr(intent.sonicPalette, axis) for axis in SONIC_AXES]
    assert vec[8:10] == [getattr(intent.vocalCharacter, axis) for axis in VOCAL_AXES]
    # Influence weights sum to 1 and land entirely in the genre buckets.
    assert sum(vec[10:]) == pytest.approx(1.0)


def test_intent_vectors_distinguish_the_personas():
    vecs = {pid: features.intent_vector(_intent(pid)) for pid in ("silt", "rust", "keep")}
    assert len({tuple(v) for v in vecs.values()}) == 3


# --- album cadence -------------------------------------------------------------


def test_album_vector_is_the_centroid_of_its_tracks():
    assert features.album_vector([[1.0, 0.0], [0.0, 1.0]]) == pytest.approx([0.5, 0.5])
    assert features.album_vector([[2.0, 4.0]]) == pytest.approx([2.0, 4.0])


def test_an_album_with_no_tracks_has_no_position():
    with pytest.raises(ValueError):
        features.album_vector([])


def test_album_influence_is_positive_when_the_new_record_moved_toward_what_it_heard():
    mine, theirs, own_prev = [1.0, 0.1], [1.0, 0.0], [0.0, 1.0]
    block = features.album_features(mine, heard={"AFAR-0002": theirs}, own_past=[own_prev])
    assert block["influence"]["AFAR-0002"] > 0


def test_album_influence_is_negative_when_the_artist_stayed_home():
    mine, theirs, own_prev = [0.0, 1.0], [1.0, 0.0], [0.1, 1.0]
    block = features.album_features(mine, heard={"AFAR-0002": theirs}, own_past=[own_prev])
    assert block["influence"]["AFAR-0002"] < 0


def test_a_debut_has_no_influence_edges_and_no_novelty():
    block = features.album_features([1.0, 0.0], heard={"AFAR-0002": [0.0, 1.0]})
    assert block["influence"] == {}  # nothing of its own to have moved from
    assert block["novelty"] == 0.0


def test_album_convergence_reads_the_new_record_against_everything_it_heard():
    same = features.album_features([1.0, 0.0], heard={"a": [1.0, 0.0], "b": [1.0, 0.0]})
    assert same["convergence"] == pytest.approx(1.0)
    apart = features.album_features([1.0, 0.0], heard={"a": [0.0, 1.0]})
    assert apart["convergence"] == pytest.approx(0.0)
    alone = features.album_features([1.0, 0.0], heard={})
    assert alone["convergence"] == pytest.approx(1.0)  # no pairs to disagree


def test_album_novelty_measures_departure_from_the_artists_own_catalogue():
    repeat = features.album_features([1.0, 0.0], heard={}, own_past=[[1.0, 0.0]])
    assert repeat["novelty"] == pytest.approx(0.0)
    departure = features.album_features([0.0, 1.0], heard={}, own_past=[[1.0, 0.0]])
    assert departure["novelty"] == pytest.approx(1.0)


def test_album_features_compute_identically_in_either_space():
    """The block is pure in its vectors — audio or intent, same function."""
    args = dict(heard={"AFAR-0002": [0.4, 0.6]}, own_past=[[0.9, 0.1]])
    assert features.album_features([0.5, 0.5], **args) == features.album_features(
        [0.5, 0.5], **args
    )


def test_the_per_round_features_are_untouched_by_the_album_cadence():
    """The experiment path still computes exactly what it always did."""
    embs = {"a": [[1.0, 0.0], [0.0, 1.0]], "b": [[0.0, 1.0], [0.0, 1.0]]}
    graph = features.influence_graph(embs, 1)
    assert set(graph) == {("a", "b"), ("b", "a")}
    assert features.convergence_curve(embs) == pytest.approx([0.0, 1.0])
