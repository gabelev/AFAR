"""The Listener: one fan, one honest word, free to disagree with the Critic.

Offline (MockProvider). Under test: the reaction's shape and valence
contract, the fan hearing ONLY the finished release (never the session log's
discards), and the artifact that carries the reception into the log.
"""

from __future__ import annotations

import json

import pytest
from ensemble.providers.model import Message, MockProvider

from afar.agents.listener import ListenerAgent, Reaction, VALENCES
from afar.config import _mock_players

_STAGE_NAMES = {"silt": "Delta Marlowe", "rust": "Roan Patina", "keep": "Evers Lane"}

_RECORD = {
    "release_id": "cccc3333dddd4444",
    "set": {"condition": "isolation", "rounds": 2, "players": ["silt", "rust", "keep"], "seed": 0},
    "rounds": [
        {
            "silt": {"line": "first coat down", "lyrics": "lay it down", "rationale": "PRIVATE-DISCARD-SILT"},
            "rust": {"line": "left the gap", "lyrics": "half the chord is missing", "rationale": "PRIVATE-DISCARD-RUST"},
            "keep": {"line": "four chords", "lyrics": "same open door", "rationale": "PRIVATE-DISCARD-KEEP"},
        },
        {
            "silt": {"line": "fifth coat anyway", "lyrics": "silt over song"},
            "rust": {"line": "worn through", "lyrics": "down to grain"},
            "keep": {"line": "back to the top", "lyrics": "we always come back"},
        },
    ],
    "staff": {
        "producer": {
            "selected": {
                "silt": {"round": 1, "take_id": "s1"},
                "rust": {"round": 1, "take_id": "r1"},
                "keep": {"round": 1, "take_id": "k1"},
            },
            "note": "One take from each act, all from the second pass.",
        },
        "critic": {
            "release_title": "Three Rooms, No Doors",
            "take_titles": {"silt": "Fifth Coat", "rust": "Down To Grain", "keep": "The Return"},
            "release_review": "Nobody moved. Isolation was the premise; it is also the result.",
            "act_reviews": {"silt": "Marlowe poured.", "rust": "Patina wore.", "keep": "Lane returned."},
        },
    },
}


def test_reaction_shape_and_valence():
    listener = ListenerAgent(MockProvider(responder=_mock_players))
    reaction = listener.react(_RECORD, stage_names=_STAGE_NAMES)
    assert isinstance(reaction, Reaction)
    assert reaction.valence in VALENCES
    assert reaction.text
    assert isinstance(reaction.disagreements_with_critic, tuple)


def test_the_fan_hears_only_the_finished_release():
    provider = MockProvider(responder=_mock_players)
    ListenerAgent(provider).react(_RECORD, stage_names=_STAGE_NAMES)
    prompt = "\n".join(m.content for m in provider.calls[-1])
    # What shipped is there: titles, the selected takes' words, the reviews.
    assert "Three Rooms, No Doors" in prompt
    assert "Fifth Coat" in prompt and "silt over song" in prompt
    assert "Nobody moved." in prompt  # the Critic's word, to agree with or not
    # The session log is not: discarded rounds' inner accounts never reach a fan.
    assert "PRIVATE-DISCARD" not in prompt
    # Stage names, not player ids, in the fan's ears.
    assert "Delta Marlowe" in prompt


def test_reaction_may_disagree_with_the_critic():
    def responder(messages):
        text = "\n".join(m.content for m in messages)
        if '"valence"' in text:
            return json.dumps(
                {
                    "valence": "loved",
                    "reaction": "The Critic heard failure; I heard three people finally left alone.",
                    "disagreements_with_critic": ["Nobody moving IS the point."],
                }
            )
        return _mock_players(messages)

    reaction = ListenerAgent(MockProvider(responder=responder)).react(_RECORD, stage_names=_STAGE_NAMES)
    assert reaction.valence == "loved"
    assert reaction.disagreements_with_critic == ("Nobody moving IS the point.",)


def test_one_truncated_reply_is_retried_not_fatal():
    # Live models occasionally return truncated JSON; the boundary retries
    # once (observed on the first live pass) and only a second failure raises.
    replies = iter(['{"valence": "mixed", "reaction": "cut off mid-', None])

    def responder(messages):
        text = "\n".join(m.content for m in messages)
        if '"valence"' in text:
            first = next(replies, None)
            if first is not None:
                return first
            return json.dumps(
                {"valence": "liked", "reaction": "Second try landed.", "disagreements_with_critic": []}
            )
        return _mock_players(messages)

    reaction = ListenerAgent(MockProvider(responder=responder)).react(_RECORD, stage_names=_STAGE_NAMES)
    assert reaction.valence == "liked"
    assert reaction.text == "Second try landed."


def test_unknown_valence_is_refused():
    def responder(messages):
        text = "\n".join(m.content for m in messages)
        if '"valence"' in text:
            return json.dumps({"valence": "lukewarm", "reaction": "eh", "disagreements_with_critic": []})
        return _mock_players(messages)

    with pytest.raises(ValueError, match="valence"):
        ListenerAgent(MockProvider(responder=responder)).react(_RECORD, stage_names=_STAGE_NAMES)


def test_execute_emits_the_reaction_artifact():
    listener = ListenerAgent(MockProvider(responder=_mock_players))
    perception = listener.perceive({"record": _RECORD, "stage_names": _STAGE_NAMES})
    artifact = listener.execute(listener.decide(perception))
    assert artifact.kind == "reaction"
    assert artifact.metadata["valence"] in VALENCES
    assert artifact.metadata["text"] == artifact.body
    assert "disagreements_with_critic" in artifact.metadata
