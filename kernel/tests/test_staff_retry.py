"""The staff retry ladder (afar.agents.robust.staff_complete).

The stranded-set lesson: one empty model reply at the frame must cost at most
a re-request, never a set. The ladder under test: (1) an empty/whitespace
reply gets one immediate re-request; (2) an unparseable reply gets one
re-prompt carrying the error and the "ONLY the JSON" nudge; (3) still bad
raises ValueError naming the stage — the caller's cue to degrade.
"""

from __future__ import annotations

import json

import pytest
from ensemble.providers.model import Message, MockProvider

from afar.agents.robust import staff_complete
from afar.intent import _loads_lenient

_MESSAGES = [
    Message(role="system", content="You are a judge."),
    Message(role="user", content="Score the rounds. Reply with ONE JSON object."),
]


def _parse(raw: str) -> dict:
    data = _loads_lenient(raw)
    if not isinstance(data, dict) or "scores" not in data:
        raise ValueError("reply is not a scores object")
    return data


def _scripted(replies: list[str]) -> MockProvider:
    replies = list(replies)

    def responder(messages):
        return replies.pop(0)

    return MockProvider(responder=responder)


def test_a_clean_reply_costs_one_call():
    provider = _scripted([json.dumps({"scores": {"0": 1}})])
    data = staff_complete(provider, _MESSAGES, stage="test/judge", parse=_parse)
    assert data == {"scores": {"0": 1}}
    assert len(provider.calls) == 1


def test_an_empty_reply_gets_one_immediate_rerequest(capsys):
    provider = _scripted(["   \n", json.dumps({"scores": {"0": 1}})])
    data = staff_complete(provider, _MESSAGES, stage="test/judge", parse=_parse)
    assert data == {"scores": {"0": 1}}
    # Two identical calls: the re-request repeats the SAME messages, no nudge.
    assert len(provider.calls) == 2
    assert provider.calls[0] == provider.calls[1]
    assert "staff_retry: test/judge: empty reply" in capsys.readouterr().out


def test_an_unparseable_reply_gets_one_nudged_reprompt(capsys):
    provider = _scripted(["Sure! Here are my thoughts.", json.dumps({"scores": {"0": 1}})])
    data = staff_complete(provider, _MESSAGES, stage="test/judge", parse=_parse)
    assert data == {"scores": {"0": 1}}
    assert len(provider.calls) == 2
    # The re-prompt carries the bad reply back and the JSON nudge.
    retry = provider.calls[1]
    assert retry[-2].role == "assistant" and retry[-2].content == "Sure! Here are my thoughts."
    assert retry[-1].role == "user"
    assert "ONLY the JSON object" in retry[-1].content
    assert "could not be used" in retry[-1].content
    assert "staff_retry: test/judge: unusable reply" in capsys.readouterr().out


def test_empty_then_garbage_then_good_climbs_the_whole_ladder():
    provider = _scripted(["", "not json at all", json.dumps({"scores": {"0": 1}})])
    data = staff_complete(provider, _MESSAGES, stage="test/judge", parse=_parse)
    assert data == {"scores": {"0": 1}}
    assert len(provider.calls) == 3


def test_a_reply_bad_twice_raises_with_the_stage_name():
    provider = _scripted(["nope", "still nope"])
    with pytest.raises(ValueError, match="test/judge: reply unusable after retries"):
        staff_complete(provider, _MESSAGES, stage="test/judge", parse=_parse)
    assert len(provider.calls) == 2  # never loops beyond the ladder


def test_the_nudge_is_configurable_for_prose_stages():
    provider = _scripted(["", "", "the note"])

    def parse(raw: str) -> str:
        if not raw.strip():
            raise ValueError("empty note")
        return raw.strip()

    note = staff_complete(
        provider, _MESSAGES, stage="producer/note", parse=parse,
        nudge="Reply again with ONLY the note text.",
    )
    assert note == "the note"
    # Empty first reply -> re-request; still empty -> parse fails -> nudged.
    assert len(provider.calls) == 3
    assert "ONLY the note text" in provider.calls[2][-1].content
