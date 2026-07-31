"""Staff-side model-call robustness: the retry ladder every staff parse climbs.

The first stranded set (20260731-175857-set-0001-contact) died at the frame:
a judge's model call returned an EMPTY reply, `_loads_lenient` raised
`intent is not valid JSON: Expecting value: ... (char 0)`, and the conductor
voided a completed, fully-paid set over one bad staff turn. The lesson, now
law (DECISIONS.md): the material always outranks the commentary — so every
staff-side parse of a model reply gets the same short ladder before anyone
is allowed to fail:

  1. an empty/whitespace reply gets ONE immediate re-request (the transient-
     hiccup case: same messages, no ceremony);
  2. a reply that will not parse gets ONE re-prompt carrying the error and a
     "reply with ONLY the JSON" nudge (the player.decide idiom);
  3. still bad -> ValueError, and the CALLER decides what degradation means
     for its stage (run_staff continues with that piece absent).

Retries are logged as `staff_retry:` lines on stdout — the same journal-
visible idiom as the render layer's `render_retry:` notes.
"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

from ensemble.providers.model import Message, ModelProvider

T = TypeVar("T")

#: The default re-prompt nudge — staff replies are JSON unless a caller says otherwise.
JSON_NUDGE = "Reply again with ONLY the JSON object — no prose, no code fences."


def staff_complete(
    model: ModelProvider,
    messages: Sequence[Message],
    *,
    stage: str,
    parse: Callable[[str], T],
    nudge: str = JSON_NUDGE,
) -> T:
    """One staff model call, with the retry ladder (see module docstring).

    `parse` turns the raw reply into the stage's value and raises ValueError
    on anything unusable — the ladder treats every ValueError the same.
    At most three model calls ever happen: first ask, empty re-request,
    nudged re-prompt. A reply that survives none of them raises ValueError
    with the stage's name on it.
    """
    messages = list(messages)
    raw = model.complete(messages)
    if not raw.strip():
        _note(stage, "empty reply — re-requesting once")
        raw = model.complete(messages)
    try:
        return parse(raw)
    except ValueError as err:
        _note(stage, f"unusable reply ({err}) — re-prompting with a nudge")
        nudged = messages + [
            Message(role="assistant", content=raw if raw.strip() else "(empty reply)"),
            Message(role="user", content=f"That reply could not be used ({err}). {nudge}"),
        ]
        retry_raw = model.complete(nudged)
        try:
            return parse(retry_raw)
        except ValueError as retry_err:
            raise ValueError(f"{stage}: reply unusable after retries: {retry_err}") from retry_err


def _note(stage: str, note: str) -> None:
    print(f"staff_retry: {stage}: {note}", flush=True)
