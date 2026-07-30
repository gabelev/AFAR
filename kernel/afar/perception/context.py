"""build_context: the ONE place the experimental manipulation lives.

Architecture rule 1 (the boundary rule): what a player may hear mid-set is
decided here and nowhere else. Every condition the experiment runs — contact,
isolation, parallel — is a different answer to "what goes in the context?",
and keeping that answer in a single chokepoint is what makes the conditions
comparable: the players, the prompts, the renderer, and the log are identical
across conditions; ONLY this function branches on `condition`.

The returned dict is deliberately double-duty: it is the exact input to
`Player.perceive` AND the exact `context` field of the logged perceptions row.
Logging what the agent saw — not a paraphrase of it — is what lets the
analysis trust the perceptions table, so the dict must stay JSON-serializable.

Conditions:
- "contact" / "social": a player hears its own previous round AND the other
  two players' previous-round material (line, intent DNA, artifact content
  hash). Round t-1 only — round-t material does not exist when the context is
  built, and the loop must never close within a round.
- "isolation" / "solo": own previous round only. Three solo artists.
- "parallel": own previous round only — identical CONTENT to isolation; the
  scheduling difference (all three still rendered simultaneously) lives in
  the runner, so parallel isolates "being run together" from "hearing each
  other". `others` is present and empty so the logged rows make the absence
  explicit rather than ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

_CONTACT_CONDITIONS: tuple[str, ...] = ("contact", "social")
_ALONE_CONDITIONS: tuple[str, ...] = ("isolation", "solo", "parallel")
CONDITIONS: tuple[str, ...] = _CONTACT_CONDITIONS + _ALONE_CONDITIONS


@dataclass(frozen=True)
class RoundEntry:
    """What one player left in the room in one round — the shareable residue.

    Only what another player is allowed to receive: the spoken line, the DNA,
    and the artifact's content hash. `rationale` stays out on purpose: it is
    logged in the intents table, but it is private reasoning, not material in
    the room.
    """

    player_id: str
    line: str
    intent: dict[str, Any]  # the DNA dict (Intent.to_dna_dict shape)
    content_hash: str  # artifact id: sha256 of the rendered bytes

    def to_context(self) -> dict[str, Any]:
        """The JSON-safe shape this entry takes inside a perceive context."""
        return {
            "player_id": self.player_id,
            "line": self.line,
            "intent": dict(self.intent),
            "content_hash": self.content_hash,
        }


class RunView:
    """The in-memory round history one runner maintains for one set.

    A list of {player_id: RoundEntry} dicts, one per COMPLETED round, in round
    order. Deliberately not a database: the JSONL ledger is the durable truth;
    this is only the live working memory `build_context` reads from.
    """

    def __init__(self) -> None:
        self.rounds: list[dict[str, RoundEntry]] = []

    def append_round(self, entries: Mapping[str, RoundEntry]) -> None:
        self.rounds.append(dict(entries))

    def entry(self, player_id: str, t: int) -> Optional[RoundEntry]:
        """One player's entry for round `t`, or None if that round never was."""
        if 0 <= t < len(self.rounds):
            return self.rounds[t].get(player_id)
        return None

    def others(self, player_id: str, t: int) -> list[RoundEntry]:
        """Every OTHER player's entry for round `t`, in stable player order."""
        if 0 <= t < len(self.rounds):
            return [e for pid, e in self.rounds[t].items() if pid != player_id]
        return []


def build_context(player_id: str, t: int, run: RunView, condition: str) -> dict[str, Any]:
    """Build what `player_id` perceives at the top of round `t`.

    THE manipulation. Returns a JSON-serializable dict that is both the
    perceive input and the logged perceptions row's `context` — see module
    docstring for what each condition admits. Raises ValueError on a condition
    it does not know: an unrecognized condition silently treated as anything
    would poison a whole run's data.
    """
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; expected one of {CONDITIONS}")

    context: dict[str, Any] = {"round": t, "condition": condition, "others": []}
    own = run.entry(player_id, t - 1)
    if own is not None:
        context["own"] = own.to_context()
    if condition in _CONTACT_CONDITIONS:
        context["others"] = [entry.to_context() for entry in run.others(player_id, t - 1)]
    return context
