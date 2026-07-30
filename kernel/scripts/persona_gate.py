"""The MERT persona-distinctness gate: can the space tell the players apart?

    cd kernel && uv run python scripts/persona_gate.py \
        --clips-per-persona 10 --threshold 0.90 --generate

Before the experiment can claim "influence moved between personas", the
measurement space has to separate the personas at all — otherwise zero
influence and an undiscriminating embedder are indistinguishable. The gate:

1. obtains N solo clips per persona — freshly generated with --generate
   (isolation condition, varied seeds, via the configured renderer), or read
   from --audio-dir DIR (either DIR/<persona>/*.mp3 subdirectories or flat
   files named <persona>-*.mp3);
2. embeds them all (MERT by default; --embedder mock proves plumbing only);
3. greedy-clusters at --threshold (features.cluster) and scores the result
   against persona identity: cluster count, per-cluster composition, PURITY,
   and mean intra- vs inter-persona cosine.

VERDICT: exit 0 iff every persona's clips majority-co-cluster (more than half
of a persona's clips land in one cluster) AND that home cluster's purity is
>= 0.8; exit 1 otherwise, naming the offender.

With --generate the same separation is also computed over intent_vector space
(no audio involved) as a secondary signal: if intents separate but audio does
not, the renderer or the embedder is blurring the personas, not the players.

Manual live script, NOT a test — the gate's logic (evaluate_gate) is what the
offline tests exercise, on synthetic vectors.
"""

from __future__ import annotations

import argparse
import os
import time
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from afar import features
from afar.agents.personas import PERSONAS
from afar.agents.player import Player
from afar.config import build_config
from afar.perception.context import RunView, build_context
from afar.perception.embedder import AudioEmbedder, MockEmbedder
from afar.run import player_seed

PURITY_MIN = 0.8
_AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


# --- gate logic (unit-tested offline on synthetic vectors) --------------------


@dataclass(frozen=True)
class GateReport:
    """One space's separation scores, plus the pass/fail verdict."""

    threshold: float
    purity_min: float
    sizes: list[int]  # cluster sizes, densest first
    composition: list[dict[str, int]]  # per cluster: persona -> member count
    majority: dict[str, bool]  # persona -> did >half its clips co-cluster?
    purity: dict[str, float]  # persona -> purity of its home cluster
    intra: float  # mean same-persona cosine
    inter: float  # mean cross-persona cosine
    passed: bool


def evaluate_gate(
    embedded: list[dict[str, Any]], *, threshold: float, purity_min: float = PURITY_MIN
) -> GateReport:
    """Score persona separation for clips carrying "persona" and "vector".

    Purity is measured on each persona's HOME cluster — the cluster holding
    the largest share of its clips — as the fraction of that cluster belonging
    to the persona. Majority + purity together mean: the persona's clips stay
    together, and what they stay with is themselves.
    """
    clusters = features.cluster(embedded, threshold)
    sizes = [len(members) for members in clusters]
    composition = [dict(Counter(m["persona"] for m in members)) for members in clusters]
    totals = Counter(item["persona"] for item in embedded)

    majority: dict[str, bool] = {}
    purity: dict[str, float] = {}
    for persona, total in sorted(totals.items()):
        home = max(range(len(clusters)), key=lambda i: composition[i].get(persona, 0))
        home_count = composition[home].get(persona, 0)
        majority[persona] = home_count * 2 > total
        purity[persona] = home_count / sizes[home]

    intra_sims: list[float] = []
    inter_sims: list[float] = []
    for a, b in combinations(embedded, 2):
        sim = features._cosine(a["vector"], b["vector"])
        (intra_sims if a["persona"] == b["persona"] else inter_sims).append(sim)
    intra = sum(intra_sims) / len(intra_sims) if intra_sims else 1.0
    inter = sum(inter_sims) / len(inter_sims) if inter_sims else 0.0

    passed = all(majority.values()) and all(p >= purity_min for p in purity.values())
    return GateReport(
        threshold=threshold,
        purity_min=purity_min,
        sizes=sizes,
        composition=composition,
        majority=majority,
        purity=purity,
        intra=intra,
        inter=inter,
        passed=passed,
    )


def render_report(space: str, report: GateReport) -> str:
    lines = [
        f"[{space} space] clusters: {len(report.sizes)} (threshold {report.threshold})",
    ]
    for i, comp in enumerate(report.composition):
        parts = ", ".join(f"{p}={n}" for p, n in sorted(comp.items()))
        lines.append(f"  cluster {i} ({report.sizes[i]} clips): {parts}")
    for persona in sorted(report.purity):
        verdict = "ok" if report.majority[persona] and report.purity[persona] >= report.purity_min else "FAIL"
        lines.append(
            f"  {persona}: majority={'yes' if report.majority[persona] else 'NO'} "
            f"purity={report.purity[persona]:.2f} [{verdict}]"
        )
    lines.append(f"  mean cosine: intra-persona {report.intra:.4f} vs inter-persona {report.inter:.4f}")
    lines.append(
        f"  gate: {'PASS' if report.passed else 'FAIL'} "
        f"(every persona majority-co-clustered with purity >= {report.purity_min})"
    )
    return "\n".join(lines)


# --- clip acquisition ---------------------------------------------------------


def _load_dotenv(path: Path) -> None:
    """Tiny KEY=VALUE loader; real env always wins over the file."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _generate_clips(config, clips_per_persona: int, seed: int) -> list[dict[str, Any]]:
    """N solo clips per persona: isolation condition, varied seeds.

    Each clip is a fresh empty-room round — no cross-perception, so whatever
    separates the clips is the persona itself, which is exactly what the gate
    is trying to measure. Keeps the Intent alongside the path so intent-space
    separation comes for free.
    """
    items: list[dict[str, Any]] = []
    for pid, persona in PERSONAS.items():
        player = Player(persona, config.model, config.renderer)
        for i in range(clips_per_persona):
            context = build_context(pid, 0, RunView(), "isolation")
            decision = player.decide(player.perceive(context))
            player.seed = player_seed(seed, pid, i)
            artifact = player.execute(decision)
            items.append(
                {
                    "id": f"{pid}-{i}",
                    "persona": pid,
                    "path": Path(artifact.body),
                    "intent": decision.data["intent"],
                }
            )
            print(f"  rendered {pid} clip {i + 1}/{clips_per_persona} -> {artifact.body}")
    return items


def _collect_clips(audio_dir: Path) -> list[dict[str, Any]]:
    """Existing clips: DIR/<persona>/* subdirs, or flat <persona>-* filenames."""
    items: list[dict[str, Any]] = []
    for pid in PERSONAS:
        sub = audio_dir / pid
        paths = sorted(sub.iterdir()) if sub.is_dir() else sorted(audio_dir.glob(f"{pid}-*"))
        paths = [p for p in paths if p.suffix.lower() in _AUDIO_SUFFIXES]
        for i, path in enumerate(paths):
            items.append({"id": f"{pid}-{i}", "persona": pid, "path": path})
    if not items:
        raise SystemExit(
            f"no clips found under {audio_dir} (expected <persona>/ subdirs or <persona>-* files)"
        )
    return items


# --- entry --------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Persona-distinctness gate over embedding space.")
    parser.add_argument("--clips-per-persona", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.90)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--generate", action="store_true",
                        help="render fresh solo clips via the configured renderer")
    source.add_argument("--audio-dir", type=Path, default=None,
                        help="use existing clips from this directory (skip generation)")
    parser.add_argument("--embedder", choices=["mock", "mert"], default="mert",
                        help="mock proves plumbing only; the gate's verdict needs mert")
    parser.add_argument("--renderer", choices=["mock", "elevenlabs"], default=None,
                        help="override AFAR_RENDERER for --generate")
    parser.add_argument("--seed", type=int, default=int(time.time()),
                        help="base seed for --generate (default: now, so clips vary)")
    args = parser.parse_args()

    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if args.renderer is not None:
        os.environ["AFAR_RENDERER"] = args.renderer

    if args.generate:
        config = build_config()
        print(f"generating {args.clips_per_persona} clips per persona "
              f"(renderer {config.renderer.name}, model {'live' if config.live else 'mock'})")
        items = _generate_clips(config, args.clips_per_persona, args.seed)
    else:
        items = _collect_clips(args.audio_dir)
        print(f"collected {len(items)} clips from {args.audio_dir}")

    embedder: AudioEmbedder
    if args.embedder == "mert":
        from afar.perception.embedder import MERTEmbedder

        embedder = MERTEmbedder()
    else:
        embedder = MockEmbedder()

    for item in items:
        item["vector"] = embedder.embed(item["path"])

    audio_report = evaluate_gate(items, threshold=args.threshold)
    print()
    print(render_report(f"audio/{embedder.name}", audio_report))

    # Secondary signal: the same separation over the DNA itself, no audio.
    if all("intent" in item for item in items):
        intent_items = [
            {"id": item["id"], "persona": item["persona"],
             "vector": features.intent_vector(item["intent"])}
            for item in items
        ]
        intent_report = evaluate_gate(intent_items, threshold=args.threshold)
        print()
        print(render_report("intent", intent_report))
    else:
        print("\n(intent space skipped: --audio-dir clips carry no intents; "
              "use --generate for the secondary signal)")

    if audio_report.passed:
        print("\nVERDICT: PASS — the embedding space distinguishes the personas.")
        return 0
    offenders = [p for p in audio_report.purity
                 if not audio_report.majority[p] or audio_report.purity[p] < audio_report.purity_min]
    print(f"\nVERDICT: FAIL — persona(s) not separated in audio space: {', '.join(offenders)}. "
          "The space cannot support influence claims at this threshold.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
