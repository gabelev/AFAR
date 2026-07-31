"""The transient-retry matrix at the urlopen seam.

The first autonomous set on the droplet died on a plain ElevenLabs 500 whose
body said "You have not been charged" — a retryable failure the adapter
treated as fatal. These tests pin the policy: 5xx and network errors retry
up to twice with escalating backoff (30s, 90s), 429 keeps its single quick
3s retry, content rejections (bad_prompt/bad_composition_plan) never retry,
non-transient HTTP errors fail fast, and the 2-slot semaphore is RELEASED
during every backoff sleep.
"""

from __future__ import annotations

import io
import urllib.error
from pathlib import Path

import pytest

import afar.render.elevenlabs as elevenlabs
from afar.intent import Influence, Intent, SonicPalette, VocalCharacter
from afar.render.elevenlabs import ElevenLabsRenderer, MusicPromptError, _RequestFailed

_500_BODY = b'{"type":"service_unavailable","message":"Something went wrong. You have not been charged"}'


def _intent() -> Intent:
    return Intent(
        seedPrompt="test artist",
        era=8,
        influences=(
            Influence("folk", 0.4),
            Influence("americana", 0.3),
            Influence("chamber pop", 0.2),
            Influence("ambient", 0.1),
        ),
        sonicPalette=SonicPalette(0, 0, 0, -1, 0, 0, 0),
        vocalCharacter=VocalCharacter(0, 0),
        lyricalObsessions=("rain",),
        visualStyle=("neon fog",),
        line="A short spoken line.",
        lyrics="rain keeps its own time",
        rationale="test",
        player_id="silt",
    ).validate()


class _Resp:
    """A successful urlopen: mp3 bytes in the body, metadata on x-* headers."""

    def __init__(self) -> None:
        self.headers = {"x-song-id": "song-1"}

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return b"\x01\x02\x03"


def _http_error(code: int, body: bytes = _500_BODY) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.test", code, "err", {}, io.BytesIO(body))


def _wire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcomes: list):
    """A renderer whose urlopen yields `outcomes` in order (exception -> raised)
    and whose backoff sleeps are recorded, not slept."""
    renderer = ElevenLabsRenderer("test-key", tmp_path / "audio")
    calls: list[object] = []
    sleeps: list[float] = []

    def fake_urlopen(req, timeout=None):
        outcome = outcomes[len(calls)]
        calls.append(req)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(elevenlabs.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(elevenlabs.time, "sleep", lambda s: sleeps.append(s))
    return renderer, calls, sleeps


def test_500_then_success_retries_with_backoff_and_succeeds(tmp_path: Path, monkeypatch, capsys):
    renderer, calls, sleeps = _wire(tmp_path, monkeypatch, [_http_error(500), _Resp()])
    result = renderer.render(_intent(), seed=7)
    assert len(calls) == 2
    assert sleeps == [30.0]
    assert result.metadata["x-song-id"] == "song-1"
    # The retry is a note in the request metadata AND on stdout.
    assert "http 500" in result.metadata["render_retry"]
    assert "render_retry" in capsys.readouterr().out


def test_three_500s_exhaust_the_retries_and_fail(tmp_path: Path, monkeypatch):
    renderer, calls, sleeps = _wire(tmp_path, monkeypatch, [_http_error(500) for _ in range(3)])
    with pytest.raises(_RequestFailed) as err:
        renderer.render(_intent(), seed=7)
    assert len(calls) == 3  # first try + 2 retries, then give up
    assert sleeps == [30.0, 90.0]  # escalating, never looping forever
    assert "You have not been charged" in str(err.value)


@pytest.mark.parametrize("code", [502, 503, 504])
def test_other_5xx_are_transient_too(tmp_path: Path, monkeypatch, code: int):
    renderer, calls, sleeps = _wire(tmp_path, monkeypatch, [_http_error(code), _Resp()])
    result = renderer.render(_intent(), seed=7)
    assert len(calls) == 2 and sleeps == [30.0]
    assert f"http {code}" in result.metadata["render_retry"]


def test_network_errors_are_transient(tmp_path: Path, monkeypatch):
    renderer, calls, sleeps = _wire(
        tmp_path, monkeypatch, [urllib.error.URLError("connection reset"), _Resp()]
    )
    result = renderer.render(_intent(), seed=7)
    assert len(calls) == 2 and sleeps == [30.0]
    assert "network error" in result.metadata["render_retry"]


def test_429_keeps_its_single_quick_retry(tmp_path: Path, monkeypatch):
    renderer, calls, sleeps = _wire(tmp_path, monkeypatch, [_http_error(429, b"{}"), _Resp()])
    result = renderer.render(_intent(), seed=7)
    assert len(calls) == 2
    assert sleeps == [3.0]  # unchanged: rate weather passes fast
    assert "http 429" in result.metadata["render_retry"]


def test_a_second_429_is_not_retried(tmp_path: Path, monkeypatch):
    renderer, calls, sleeps = _wire(
        tmp_path, monkeypatch, [_http_error(429, b"{}") for _ in range(2)]
    )
    with pytest.raises(_RequestFailed):
        renderer.render(_intent(), seed=7)
    assert len(calls) == 2 and sleeps == [3.0]


def test_music_prompt_error_is_never_retried(tmp_path: Path, monkeypatch):
    body = (
        b'{"detail": {"status": "bad_prompt", "suggestion": "sing about weather",'
        b' "message": "rejected"}}'
    )
    renderer, calls, sleeps = _wire(tmp_path, monkeypatch, [_http_error(400, body)])
    with pytest.raises(MusicPromptError) as err:
        renderer.render(_intent(), seed=7)
    assert len(calls) == 1 and sleeps == []  # content, not weather
    assert err.value.suggestion == "sing about weather"


def test_non_transient_http_errors_fail_fast(tmp_path: Path, monkeypatch):
    renderer, calls, sleeps = _wire(
        tmp_path, monkeypatch, [_http_error(401, b'{"detail": {"status": "invalid_api_key"}}')]
    )
    with pytest.raises(_RequestFailed):
        renderer.render(_intent(), seed=7)
    assert len(calls) == 1 and sleeps == []


def test_semaphore_is_released_during_backoff_sleeps(tmp_path: Path, monkeypatch):
    """The slot probe: during EVERY backoff sleep both semaphore slots must be
    acquirable — a render that is only waiting must never starve the other
    slot's work."""
    renderer, calls, sleeps = _wire(
        tmp_path, monkeypatch, [_http_error(500), _http_error(429, b"{}"), _Resp()]
    )
    probes: list[list[bool]] = []

    def probing_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        slots = [elevenlabs._semaphore.acquire(blocking=False) for _ in range(2)]
        probes.append(slots)
        for got in slots:
            if got:
                elevenlabs._semaphore.release()

    monkeypatch.setattr(elevenlabs.time, "sleep", probing_sleep)
    renderer.render(_intent(), seed=7)
    assert sleeps == [30.0, 3.0]
    assert probes == [[True, True], [True, True]]
