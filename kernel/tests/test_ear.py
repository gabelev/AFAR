"""Measured hearing: the ear's pure functions, the prompt block, the round loop.

The acts perceive what other takes actually SOUND like — facts derived from
the audio (DSP buckets) and from the very embedding vectors the round logged
(the relations). These tests pin the tercile buckets, the toward/away sign,
the degradation doctrine (no librosa, unreadable bytes -> relations only,
never a blocked round), the WHAT YOU HEARD prompt rendering, and the offline
round-loop integration: heard dicts ride the perceptions rows, deterministic
under mocks, and always consistent with the logged embeddings.
"""

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from ensemble.agent import Perception
from ensemble.providers.model import MockProvider

from afar.agents.personas import PERSONAS
from afar.agents.player import Player, _heard_sentence
from afar.config import AfarConfig, _mock_players
from afar.features import _cosine
from afar.log import JsonlLedger, RunContext
from afar.perception.ear import BRIGHTNESS_LABELS, HEARD_KEYS, LOUDNESS_LABELS, dsp_facts, hear, tercile
from afar.perception.embedder import MockEmbedder
from afar.render.base import MockRenderer
from afar.run import run_set

_PLAYERS = ("silt", "rust", "keep")

_DSP = {"tempo_bpm": 98.0, "rms": 0.01, "centroid_hz": 900.0, "duration_s": 60.0}


# --- tercile buckets: quiet/mid/loud are comparisons vs the set so far ---------


def test_terciles_split_the_pool_bottom_middle_top():
    pool = [0.01, 0.05, 0.2]
    assert tercile(0.01, pool, LOUDNESS_LABELS) == "quiet"
    assert tercile(0.05, pool, LOUDNESS_LABELS) == "mid"
    assert tercile(0.2, pool, LOUDNESS_LABELS) == "loud"
    assert tercile(900.0, [900.0, 2000.0, 5000.0], BRIGHTNESS_LABELS) == "dark"
    assert tercile(5000.0, [900.0, 2000.0, 5000.0], BRIGHTNESS_LABELS) == "bright"


def test_terciles_with_nothing_to_compare_read_as_mid():
    # Fewer than three takes, or a pool with zero spread: "quiet" is a
    # comparison, and with no comparison the honest bucket is the middle one.
    assert tercile(0.5, [0.5], LOUDNESS_LABELS) == "mid"
    assert tercile(0.5, [0.5, 0.9], LOUDNESS_LABELS) == "mid"
    assert tercile(0.5, [0.5, 0.5, 0.5, 0.5], LOUDNESS_LABELS) == "mid"


# --- hear: the pure function ---------------------------------------------------


def _ctx(**over):
    base = {
        "your_vec": [1.0, 0.0],
        "your_prev_vec": [1.0, 0.0],
        "their_prev_vec": [0.0, 1.0],
        "rms_pool": [0.01, 0.05, 0.2],
        "centroid_pool": [900.0, 2000.0, 5000.0],
        "dsp": dict(_DSP),
    }
    base.update(over)
    return base


def test_hear_reports_dsp_facts_and_relations():
    take = [1.0, 0.1]  # close to YOUR last take, far from their own previous
    heard = hear(Path("/nonexistent.mp3"), take, _ctx())
    assert set(heard) == set(HEARD_KEYS)
    assert heard["tempo_bpm"] == 98.0
    assert heard["loudness"] == "quiet"
    assert heard["brightness"] == "dark"
    assert heard["duration_s"] == 60.0
    assert heard["distance_to_yours"] == round(1.0 - _cosine(take, [1.0, 0.0]), 4)
    assert heard["distance_to_their_last"] == round(1.0 - _cosine(take, [0.0, 1.0]), 4)
    assert heard["moved"] == "toward_you"
    assert json.loads(json.dumps(heard)) == heard  # rides a perceptions row


def test_hear_reads_the_influence_sign_as_toward_or_away():
    toward = hear(Path("/x"), [1.0, 0.1], _ctx())
    away = hear(Path("/x"), [0.1, 1.0], _ctx())
    assert toward["moved"] == "toward_you"
    assert away["moved"] == "away_from_you"


def test_hear_without_previous_round_reports_no_movement():
    # The set's first round: there is no "since last round" yet.
    heard = hear(Path("/x"), [1.0, 0.1], _ctx(your_prev_vec=None, their_prev_vec=None))
    assert heard["moved"] is None
    assert heard["distance_to_their_last"] is None
    assert heard["distance_to_yours"] is not None


def test_hear_degrades_to_relations_only_when_dsp_failed():
    # dsp=None is the runner saying "measurement failed" — the MERT relations
    # still carry the dict, and nothing raises.
    heard = hear(Path("/x"), [1.0, 0.1], _ctx(dsp=None))
    assert heard["tempo_bpm"] is None
    assert heard["loudness"] is None
    assert heard["brightness"] is None
    assert heard["duration_s"] is None
    assert heard["moved"] == "toward_you"
    assert heard["distance_to_yours"] is not None


def test_dsp_facts_on_unreadable_bytes_is_none_never_an_error(tmp_path: Path):
    junk = tmp_path / "take.mp3"
    junk.write_bytes(b"MOCKAUDIO not audio at all")
    assert dsp_facts(junk) is None
    assert dsp_facts(tmp_path / "missing.mp3") is None


def test_dsp_facts_measures_a_real_wav_when_librosa_is_installed(tmp_path: Path):
    pytest.importorskip("librosa")
    sr, seconds = 22050, 2.0
    path = tmp_path / "sine.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        frames = int(sr * seconds)
        f.writeframes(
            b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / sr)))
                for i in range(frames)
            )
        )
    facts = dsp_facts(path)
    assert facts is not None
    assert facts["duration_s"] == pytest.approx(2.0, abs=0.1)
    assert facts["rms"] > 0
    assert facts["centroid_hz"] > 0
    assert facts["tempo_bpm"] >= 0


# --- the WHAT YOU HEARD prompt block -------------------------------------------

_HEARD = {
    "tempo_bpm": 98.0,
    "loudness": "quiet",
    "brightness": "dark",
    "duration_s": 60.0,
    "distance_to_yours": 0.41,
    "distance_to_their_last": 0.12,
    "moved": "away_from_you",
}


def _player() -> Player:
    return Player(
        PERSONAS["silt"], MockProvider(responder=_mock_players), MockRenderer(Path("/tmp/unused"))
    )


def test_heard_sentence_is_the_terse_studio_line():
    assert _heard_sentence("Roan", _HEARD) == (
        "Roan's last take: about 98 BPM, quiet, dark, 60 seconds. "
        "It moved away from yours — closer to their own last one."
    )


def test_heard_sentence_degrades_to_what_was_measured():
    relations_only = {**_HEARD, "tempo_bpm": None, "loudness": None, "brightness": None, "duration_s": None}
    assert _heard_sentence("Roan", relations_only) == (
        "Roan's last take: It moved away from yours — closer to their own last one."
    )
    nothing = dict.fromkeys(_HEARD)
    assert _heard_sentence("Roan", nothing) is None
    mid = {**_HEARD, "loudness": "mid", "brightness": "mid", "moved": "toward_you"}
    assert _heard_sentence("Evers", mid) == (
        "Evers's last take: about 98 BPM, mid loudness, mid brightness, 60 seconds. "
        "It moved toward yours — away from their own last one."
    )


def test_decision_prompt_renders_the_heard_block_and_strips_it_from_the_room():
    context = {
        "round": 2,
        "condition": "contact",
        "others": [
            {"player_id": "rust", "line": "cut it", "intent": {}, "content_hash": "h1",
             "heard": dict(_HEARD)},
            {"player_id": "keep", "line": "held it", "intent": {}, "content_hash": "h2"},
        ],
    }
    prompt = _player()._decision_prompt(Perception(data=context))
    assert "WHAT YOU HEARD (measured from the audio of their last takes):" in prompt
    assert (
        "Roan's last take: about 98 BPM, quiet, dark, 60 seconds. "
        "It moved away from yours — closer to their own last one." in prompt
    )
    # One fact said once: the raw dict does not also ride the room JSON.
    assert '"heard"' not in prompt
    assert '"tempo_bpm"' not in prompt
    # The room itself still carries the material.
    assert '"cut it"' in prompt and '"held it"' in prompt
    # First names, never player ids, address the heard block.
    assert "rust's last take" not in prompt


def test_prompt_without_heard_facts_has_no_heard_block():
    context = {
        "round": 1,
        "condition": "contact",
        "others": [{"player_id": "rust", "line": "cut it", "intent": {}, "content_hash": "h1"}],
    }
    prompt = _player()._decision_prompt(Perception(data=context))
    assert "WHAT YOU HEARD" not in prompt


def test_personas_carry_the_trust_your_ears_contract():
    for persona in PERSONAS.values():
        assert "Trust your ears" in persona.base_prompt


# --- round-loop integration: offline, deterministic, consistent with the log ---


def _run(tmp_path: Path, *, name: str = "one", condition: str = "contact", rounds: int = 3):
    root = tmp_path / name
    renderer = MockRenderer(root / "audio")
    config = AfarConfig(
        model=MockProvider(responder=_mock_players),
        renderer=renderer,
        runs_root=root,
        live=False,
        code_sha="test-sha",
    )
    ledger = JsonlLedger(root, f"{name}-run", context=RunContext(code_sha="test-sha"))
    players = [Player(PERSONAS[pid], config.model, renderer) for pid in _PLAYERS]
    result = run_set(
        players,
        rounds=rounds,
        condition=condition,
        config=config,
        ledger=ledger,
        embedder=MockEmbedder(),
        seed=11,
    )
    return result, ledger


def _rows(ledger: JsonlLedger, table: str) -> list[dict]:
    path = ledger.run_dir / f"{table}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_contact_perceptions_carry_heard_dicts_from_round_one_on(tmp_path: Path):
    _, ledger = _run(tmp_path)
    for row in _rows(ledger, "perceptions"):
        if row["round"] == 0:
            assert row["context"]["others"] == []
            continue
        assert len(row["context"]["others"]) == 2
        for entry in row["context"]["others"]:
            heard = entry["heard"]
            assert set(heard) == set(HEARD_KEYS)
            assert isinstance(heard["distance_to_yours"], float)
            # Mock bytes are unmeasurable audio: DSP degrades to None and the
            # relations carry the dict — the round was never blocked.
            assert heard["tempo_bpm"] is None
            assert heard["loudness"] is None
            if row["round"] == 1:
                # The first takes had no "last round" to have moved since.
                assert heard["moved"] is None
                assert heard["distance_to_their_last"] is None
            else:
                assert heard["moved"] in ("toward_you", "away_from_you", None)
                assert isinstance(heard["distance_to_their_last"], float)


def test_heard_relations_match_the_logged_embeddings_exactly(tmp_path: Path):
    # The no-drift care point: what the ear told the acts must be recomputable
    # from the embeddings rows the same round logged — same vectors, same math.
    _, ledger = _run(tmp_path)
    vecs = {
        (row["player"], row["round"]): row["vector"]
        for row in _rows(ledger, "embeddings")
        if row["space"] == "audio"
    }
    checked = 0
    for row in _rows(ledger, "perceptions"):
        listener, t = row["player"], row["round"]
        for entry in row["context"]["others"]:
            heard, maker = entry["heard"], entry["player_id"]
            take = vecs[(maker, t - 1)]
            assert heard["distance_to_yours"] == round(1.0 - _cosine(take, vecs[(listener, t - 1)]), 4)
            if t >= 2:
                assert heard["distance_to_their_last"] == round(
                    1.0 - _cosine(take, vecs[(maker, t - 2)]), 4
                )
            checked += 1
    assert checked == 2 * 3 * 2  # 2 hearing rounds x 3 listeners x 2 others


@pytest.mark.parametrize("condition", ["isolation", "parallel"])
def test_alone_conditions_never_carry_heard(tmp_path: Path, condition: str):
    _, ledger = _run(tmp_path, name=condition, condition=condition)
    for row in _rows(ledger, "perceptions"):
        assert row["context"]["others"] == []
        assert "heard" not in json.dumps(row["context"])


def test_mock_heard_dicts_are_deterministic_across_identical_runs(tmp_path: Path):
    _, one = _run(tmp_path, name="one")
    _, two = _run(tmp_path, name="two")
    contexts_one = [row["context"] for row in _rows(one, "perceptions")]
    contexts_two = [row["context"] for row in _rows(two, "perceptions")]
    assert contexts_one == contexts_two
