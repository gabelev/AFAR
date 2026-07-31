"""ElevenLabs music_v2 adapter for the Renderer seam.

Port of afar_music's `lib/generation/music.ts`, rebuilt stdlib-only (urllib)
in the style of ensemble's AnthropicProvider so the kernel keeps zero runtime
dependencies. Built to the verified API facts (afar_music docs/SPEC.md):

- model pinned to music_v2; composition plan, not a one-shot prompt
- the body carries ONLY model_id + composition_plan: all style direction and
  context_adherence live inside the plan's chunks (music_v2 schema);
  respect_sections_durations is music_v1-only and is not sent
- the response BODY is raw mp3 audio; track metadata is on `x-*` response
  headers
- ~5-6s generation for a 30s track; 90s timeout leaves headroom
- bad_prompt / bad_composition_plan rejections carry a suggested replacement —
  raised as MusicPromptError and NEVER retried (the suggestion is a creative
  decision that belongs to the caller, not this adapter)
- transient failures ARE retried: 429 gets its single 3s retry (rate weather
  passes fast), and 5xx / network errors get up to 2 retries at 30s then 90s
  (the API's own 500 says "You have not been charged" — the request is safe
  to repeat). Every retry is printed and noted in the result metadata as
  `render_retry`. Anything else (401, 404, ...) fails fast.
- the subscription allows 2 concurrent generations; a third concurrent call
  429s (concurrent_limit_exceeded). The module-level semaphore below queues
  the overflow transparently. It is PROCESS-LOCAL: two kernel processes
  sharing one key can still trip the API limit. The semaphore wraps ONLY the
  in-flight request — backoff sleeps happen with the slot released, so a
  render waiting out a 500 never starves the other slot's work.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from afar.intent import Intent
from afar.mapping import build_composition_plan
from afar.render.base import RenderResult, chunk_lyrics

_MUSIC_URL = "https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128"
_TIMEOUT_S = 90.0
_MAX_CONCURRENT = 2
_RETRY_AFTER_429_S = 3.0  # rate weather passes fast; one quick retry
_TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})
_TRANSIENT_BACKOFF_S = (30.0, 90.0)  # 5xx / network: up to 2 retries, escalating

# Process-local concurrency gate (see module docstring).
_semaphore = threading.Semaphore(_MAX_CONCURRENT)


class MusicPromptError(Exception):
    """A content rejection (bad_prompt / bad_composition_plan) carrying the
    API's suggested replacement. Never auto-retried: retrying the same plan
    yields the same rejection, and applying the suggestion silently would put
    words in a player's mouth. Surface `.suggestion` to the caller."""

    def __init__(self, code: str, suggestion: Optional[str], message: str) -> None:
        super().__init__(message)
        self.code = code  # "bad_prompt" | "bad_composition_plan"
        self.suggestion = suggestion


class _RequestFailed(RuntimeError):
    """A non-content request failure; carries the status so transient codes
    (429, 5xx) can be retried. status_code 0 means a network-level error
    (URLError) that never produced an HTTP status — treated as transient."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def transient(self) -> bool:
        return self.status_code == 0 or self.status_code in _TRANSIENT_STATUSES


class ElevenLabsRenderer:
    """Renderer backed by the ElevenLabs music_v2 endpoint.

    `seed` is recorded in provenance by the caller but not sent: music_v2
    exposes no seed control, so live renders are non-deterministic by nature.
    `continue_from` raises: musical continuity in AFAR must come from players
    hearing each other, never from conditioning_ref smuggling audio across
    the perceive boundary.
    """

    name = "elevenlabs"

    def __init__(self, api_key: str, out_dir: Path, *, timeout: float = _TIMEOUT_S) -> None:
        if not api_key:
            raise ValueError("ElevenLabsRenderer requires an api_key")
        self.api_key = api_key
        self.out_dir = Path(out_dir)
        self.timeout = timeout

    def render(
        self, intent: Intent, *, seed: int, continue_from: Optional[Path] = None
    ) -> RenderResult:
        if continue_from is not None:
            raise NotImplementedError(
                "continue_from is unsupported: continuity must come through perception, "
                "never conditioning_ref"
            )

        built = build_composition_plan(intent, chunk_lyrics(intent))
        # ONLY model_id + composition_plan: context_adherence rides inside the
        # plan's chunk, and respect_sections_durations is music_v1-only — both
        # used to be sent at the top level, where music_v2 silently ignores them.
        body = json.dumps(
            {
                "model_id": "music_v2",
                "composition_plan": built.plan,
            }
        ).encode("utf-8")
        # The sha of the EXACT request bytes: what the API was actually asked.
        prompt_sha = hashlib.sha256(body).hexdigest()

        # Retry policy: 429 keeps its single quick retry; 5xx/network errors
        # get up to 2 escalating retries (the API's 500 explicitly says the
        # request was not charged). MusicPromptError is content, not weather,
        # and propagates untouched. Each backoff sleep happens OUTSIDE the
        # semaphore — a slot is never held by a render that is only waiting.
        retried_429 = 0
        retried_transient = 0
        retry_notes: list[str] = []
        while True:
            with _semaphore:
                try:
                    audio, metadata = self._post(body)
                    break
                except _RequestFailed as err:
                    if err.status_code == 429 and retried_429 < 1:
                        retried_429 += 1
                        delay = _RETRY_AFTER_429_S
                    elif err.transient and retried_transient < len(_TRANSIENT_BACKOFF_S):
                        delay = _TRANSIENT_BACKOFF_S[retried_transient]
                        retried_transient += 1
                    else:
                        raise
                    note = (
                        f"{'http ' + str(err.status_code) if err.status_code else 'network error'}"
                        f" — retrying in {delay:.0f}s"
                        f" (retry {retried_429 + retried_transient})"
                    )
            # Slot released: the backoff never blocks the other render.
            retry_notes.append(note)
            print(f"render_retry: {note}", flush=True)
            time.sleep(delay)
        if retry_notes:
            metadata["render_retry"] = "; ".join(retry_notes)

        content_hash = hashlib.sha256(audio).hexdigest()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{content_hash}.mp3"
        path.write_bytes(audio)

        return RenderResult(
            path=path,
            content_hash=content_hash,
            renderer_version="elevenlabs-music_v2",
            prompt_sha=prompt_sha,
            metadata=metadata,
        )

    # -- internals -------------------------------------------------------------

    def _post(self, body: bytes) -> tuple[bytes, dict[str, Any]]:
        req = urllib.request.Request(
            _MUSIC_URL,
            data=body,
            method="POST",
            headers={"xi-api-key": self.api_key, "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                audio = resp.read()
                # The body is the audio itself; metadata rides on x-* headers.
                metadata = {
                    key.lower(): value
                    for key, value in resp.headers.items()
                    if key.lower().startswith("x-")
                }
                return audio, metadata
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            detail: dict[str, Any] = {}
            try:
                parsed = json.loads(text)
                raw_detail = parsed.get("detail", parsed) if isinstance(parsed, dict) else {}
                if isinstance(raw_detail, dict):
                    detail = raw_detail
            except json.JSONDecodeError:
                pass  # bare 500s (e.g. chunk text over ~200 chars) have no JSON body
            status = detail.get("status")
            if status in ("bad_prompt", "bad_composition_plan"):
                raise MusicPromptError(
                    status,
                    detail.get("suggestion"),
                    detail.get("message")
                    or f"ElevenLabs rejected the composition plan ({status})",
                ) from e
            raise _RequestFailed(
                e.code, f"ElevenLabs music request failed ({e.code}): {text[:300]}"
            ) from e
        except urllib.error.URLError as e:
            # No HTTP status at all (DNS, refused connection, timeout):
            # status_code 0 marks it transient for the retry loop above.
            raise _RequestFailed(0, f"ElevenLabs music request failed: {e.reason}") from e
