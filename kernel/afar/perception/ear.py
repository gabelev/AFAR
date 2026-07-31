"""Measured hearing: what another act's take actually SOUNDED like.

Tier 1 of the audio-perception ladder. In contact rounds each player is told,
per other act, a handful of MEASURED facts about that act's previous-round
take — derived from the audio itself, never from what the act said about it.
Two kinds of fact:

- DSP facts (librosa, the `listen` extra): tempo, a loudness bucket, a
  brightness bucket, duration. Buckets are terciles vs. the set so far —
  "quiet" means quiet FOR THIS SET, which is the only sense a musician in the
  room could mean.
- Relational facts from the audio-embedding space: cosine distance from the
  take to the listener's own last take, distance to the maker's previous
  take, and the sign of the influence integrand — did they move toward you or
  away since last round, phrased as perception.

The relations are computed from the SAME embedding vectors run_set logs that
round (the caller passes them in), so what the ear reports and what
features.py later computes can never drift apart.

Degradation doctrine: DSP is optional equipment. librosa missing (the mock /
offline path never requires it) or unable to read the file (mock bytes) means
the DSP facts are None and the MERT relations carry the whole dict — a failed
`dsp_facts` never blocks a round. `hear` itself is pure: everything it needs
arrives as arguments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from afar.features import _cosine, influence

LOUDNESS_LABELS: tuple[str, str, str] = ("quiet", "mid", "loud")
BRIGHTNESS_LABELS: tuple[str, str, str] = ("dark", "mid", "bright")

#: Every key a heard dict may carry — the whitelist the context test pins.
HEARD_KEYS: tuple[str, ...] = (
    "tempo_bpm",
    "loudness",
    "brightness",
    "duration_s",
    "distance_to_yours",
    "distance_to_their_last",
    "moved",
)


def dsp_facts(path: Path) -> Optional[dict[str, float]]:
    """Raw DSP facts of one audio file, or None if they cannot be measured.

    Lazy librosa import (the `listen` extra): the mock/offline path must not
    require it. ANY failure — librosa absent, unreadable bytes, an empty
    file — returns None; the ear degrades to the embedding relations only.
    Transient read (rule 6): the waveform is decoded, measured, discarded.
    """
    try:
        import numpy as np  # librosa's own hard dependency
        import librosa

        wav, sr = librosa.load(str(path), sr=None, mono=True)
        if wav.size == 0:
            return None
        tempo, _ = librosa.beat.beat_track(y=wav, sr=sr)
        return {
            "tempo_bpm": round(float(np.asarray(tempo).reshape(-1)[0]), 1),
            "rms": float(np.mean(librosa.feature.rms(y=wav))),
            "centroid_hz": float(np.mean(librosa.feature.spectral_centroid(y=wav, sr=sr))),
            "duration_s": round(wav.size / float(sr), 1),
        }
    except Exception:
        return None


def tercile(value: float, pool: Sequence[float], labels: Sequence[str]) -> str:
    """Bucket `value` against the set-so-far `pool` (which includes it).

    Terciles by rank: bottom third of the pool -> labels[0], top third ->
    labels[2]. Fewer than three takes — or a pool with no spread at all —
    reads as the middle label: "quiet" is a comparison, and with nothing to
    compare against the honest answer is "mid".
    """
    vals = sorted(pool)
    if len(vals) < 3 or vals[0] == vals[-1]:
        return labels[1]
    lo = vals[len(vals) // 3]
    hi = vals[(2 * len(vals)) // 3]
    if value < lo:
        return labels[0]
    if value >= hi:
        return labels[2]
    return labels[1]


def hear(
    take_audio_path: Path,
    mert_vec: Sequence[float],
    listener_ctx: Mapping[str, Any],
) -> dict[str, Any]:
    """One take, heard by one listener: the measured `heard` dict, JSON-safe.

    `mert_vec` is the take's audio-space embedding EXACTLY as logged that
    round — the caller passes the logged vector, so the ear's relations and
    features.py's influence numbers are computed from the same coordinates.

    `listener_ctx` keys (all optional except `your_vec`; None where a fact
    does not exist yet):
      - "your_vec": the listener's own same-round vector (their "last take"
        at perceive time, when this dict reaches them next round).
      - "your_prev_vec" / "their_prev_vec": the previous round's vectors, for
        the moved-toward-or-away sign. None in the set's first round.
      - "rms_pool" / "centroid_pool": the set-so-far values the buckets are
        terciles of (each pool includes this take's own value).
      - "dsp": precomputed `dsp_facts` for this take (run_set measures each
        take once and shares the result across both listeners). Absent means
        measure `take_audio_path` here; None means measurement failed —
        degrade to the relations.

    Never raises past a bad audio file: DSP fields are None when unmeasured;
    the relations are None only when the vector they need does not exist.
    """
    dsp = listener_ctx["dsp"] if "dsp" in listener_ctx else dsp_facts(take_audio_path)

    heard: dict[str, Any] = {
        "tempo_bpm": None,
        "loudness": None,
        "brightness": None,
        "duration_s": None,
        "distance_to_yours": None,
        "distance_to_their_last": None,
        "moved": None,
    }
    if dsp is not None:
        heard["tempo_bpm"] = dsp["tempo_bpm"]
        heard["duration_s"] = dsp["duration_s"]
        heard["loudness"] = tercile(dsp["rms"], listener_ctx.get("rms_pool") or [dsp["rms"]], LOUDNESS_LABELS)
        heard["brightness"] = tercile(
            dsp["centroid_hz"], listener_ctx.get("centroid_pool") or [dsp["centroid_hz"]], BRIGHTNESS_LABELS
        )

    your_vec = listener_ctx.get("your_vec")
    your_prev = listener_ctx.get("your_prev_vec")
    their_prev = listener_ctx.get("their_prev_vec")
    if your_vec is not None:
        heard["distance_to_yours"] = round(1.0 - _cosine(mert_vec, your_vec), 4)
    if their_prev is not None:
        heard["distance_to_their_last"] = round(1.0 - _cosine(mert_vec, their_prev), 4)
    if your_prev is not None and their_prev is not None:
        # The influence integrand, phrased as perception: did their new take
        # move toward what YOU had just played, or stay closer to their own?
        pull = influence(mert_vec, your_prev, their_prev)
        if pull > 1e-9:
            heard["moved"] = "toward_you"
        elif pull < -1e-9:
            heard["moved"] = "away_from_you"
    return heard
