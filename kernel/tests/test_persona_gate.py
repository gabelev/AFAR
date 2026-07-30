"""Persona gate logic on synthetic embeddings — no MERT, no audio, no network.

The gate script's verdict function (evaluate_gate) is what decides whether the
experiment's measurement space is usable at all, so its pass/fail behaviour is
pinned here on hand-built vectors: cleanly separated personas must pass,
label-shuffled ones must fail.
"""

import importlib.util
import sys
from pathlib import Path

_GATE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "persona_gate.py"
_spec = importlib.util.spec_from_file_location("persona_gate", _GATE_PATH)
persona_gate = importlib.util.module_from_spec(_spec)
# Registered before exec: @dataclass resolves types via sys.modules[__module__].
sys.modules["persona_gate"] = persona_gate
_spec.loader.exec_module(persona_gate)

_CLIPS_PER_PERSONA = 5


def _separated_clips() -> list[dict]:
    """Three personas on three near-orthogonal axes, small in-persona jitter."""
    bases = {"silt": 0, "rust": 1, "keep": 2}
    items = []
    for persona, axis in bases.items():
        for i in range(_CLIPS_PER_PERSONA):
            vector = [0.0, 0.0, 0.0]
            vector[axis] = 1.0
            vector[(axis + 1) % 3] = 0.05 * i  # jitter, still ~cos 1 to its base
            items.append({"id": f"{persona}-{i}", "persona": persona, "vector": vector})
    return items


def test_cleanly_separated_personas_pass_the_gate():
    report = persona_gate.evaluate_gate(_separated_clips(), threshold=0.9)
    assert report.passed
    assert len(report.sizes) == 3
    assert all(report.majority.values())
    assert all(purity >= 0.8 for purity in report.purity.values())
    assert report.intra > report.inter


def test_shuffled_labels_fail_the_gate():
    # Same vectors, persona labels dealt round-robin across the true clusters:
    # no persona keeps a majority anywhere, so the space "knows" nothing.
    items = _separated_clips()
    labels = ("silt", "rust", "keep")
    for i, item in enumerate(items):
        item["persona"] = labels[i % 3]
    report = persona_gate.evaluate_gate(items, threshold=0.9)
    assert not report.passed
    assert not all(report.majority.values())
    assert report.intra < report.inter  # the labels no longer explain the space


def test_purity_reflects_cluster_contamination():
    # One rust clip sits exactly on silt's axis: silt's home cluster is 5/6
    # silt, so purity ~0.83; rust keeps a 4/5 majority elsewhere.
    items = _separated_clips()
    items.append({"id": "rust-stray", "persona": "rust", "vector": [1.0, 0.0, 0.0]})
    report = persona_gate.evaluate_gate(items, threshold=0.9)
    assert report.purity["silt"] < 1.0
    assert report.majority["rust"]
