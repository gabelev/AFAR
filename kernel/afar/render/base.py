"""The Renderer seam: every path from an Intent to bytes on disk goes here.

Mirrors ensemble's ModelProvider pattern: agents never talk to a music API
directly, they call a `Renderer`. That keeps the whole kernel testable on
`MockRenderer` (deterministic bytes, zero network) and lets the live
ElevenLabs adapter swap in via config without touching player code.

Artifacts are content-addressed: `content_hash` is the sha256 of the produced
file's bytes and doubles as the artifact id in the log. `prompt_sha` hashes
the exact request that produced the audio, so a logged track can always be
traced to (and re-issued as) the request that made it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from afar.intent import Intent
from afar.mapping import build_composition_plan


@dataclass(frozen=True)
class RenderResult:
    """What a render produced: a file, and enough provenance to reproduce it."""

    path: Path
    content_hash: str  # sha256 of the file bytes; the artifact id
    renderer_version: str
    prompt_sha: str  # sha256 of the exact request that produced the audio
    metadata: Mapping[str, Any] = field(default_factory=dict)


def chunk_lyrics(intent: Intent) -> str:
    """The chunk text for a render: the player's sung lyrics.

    Falls back to the spoken line only for pre-lyrics intents (older logged
    rows re-rendered); validate() keeps live lyrics non-empty. Clamping to the
    API's character limit happens inside build_composition_plan.
    """
    return intent.lyrics if intent.lyrics.strip() else intent.line


#: The default take length in seconds — what every render assumes unless the
#: Producer's direction says otherwise.
DEFAULT_DURATION_S = 30


@runtime_checkable
class Renderer(Protocol):
    """Intent -> audio file. `duration_s` is the Producer's session length
    (default 30s — every pre-direction caller keeps its behavior).
    `continue_from` is reserved for future continuity schemes; Step A
    renderers refuse it rather than fake it."""

    name: str

    def render(
        self,
        intent: Intent,
        *,
        seed: int,
        duration_s: int = DEFAULT_DURATION_S,
        continue_from: Optional[Path] = None,
    ) -> RenderResult: ...


class MockRenderer:
    """A deterministic, offline Renderer for tests and mock runs.

    The bytes are a pure function of (intent content hash, seed): same intent
    and seed always produce the same file, so tests can assert content
    addressing end-to-end without any audio stack. prompt_sha hashes the same
    composition-plan payload the live renderer would send, so the log rows a
    mock run produces have the same shape and meaning as live ones.
    """

    name = "mock"

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)

    def render(
        self,
        intent: Intent,
        *,
        seed: int,
        duration_s: int = DEFAULT_DURATION_S,
        continue_from: Optional[Path] = None,
    ) -> RenderResult:
        if continue_from is not None:
            raise NotImplementedError("continuity is not supported in Step A renderers")

        built = build_composition_plan(intent, chunk_lyrics(intent), duration_ms=duration_s * 1000)
        # Same body shape as the live renderer: ONLY model_id + composition_plan
        # (context_adherence lives inside the plan's chunk in music_v2).
        prompt_payload = {
            "model_id": "music_v2",
            "composition_plan": built.plan,
        }
        prompt_sha = hashlib.sha256(
            json.dumps(prompt_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        block = hashlib.sha256(f"{intent.content_hash()}:{seed}".encode("utf-8")).digest()
        # Byte length scales with duration (32 blocks per 30s: ~1KB at the
        # default, byte-identical to the pre-duration mock at 30s) so tests
        # can see a longer take in the artifact itself.
        audio = b"afar-mock-track\n" + block * (32 * duration_s // DEFAULT_DURATION_S)
        content_hash = hashlib.sha256(audio).hexdigest()

        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{content_hash}.mp3"
        path.write_bytes(audio)

        return RenderResult(
            path=path,
            content_hash=content_hash,
            renderer_version="mock",
            prompt_sha=prompt_sha,
            metadata={
                "composition_plan": built.plan,
                "context_adherence": built.context_adherence,
                "provenance": built.provenance,
                "seed": seed,
                "duration_s": duration_s,
            },
        )
