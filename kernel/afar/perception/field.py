"""The Muse's PERCEIVE wiring: how the outside world reaches AFAR at all.

Architecture rule 2: the world enters through the brief, never the ear. This
module is the world side of that door — search adapters, provenance, and the
evidence -> fragment conversion that feeds the Muse's stigmergic ledger.
Mirrors mold/perception_web.py over the same framework seams
(ensemble.perceive): the mechanics (recency contract, date injection, dedup)
live in ensemble; only AFAR's surfaces and beats live here.

Beats (what makes the Muse's clustering legible):
  BEAT_FIELD     — the discourse: what is moving in music outside AFAR.
  BEAT_OWN       — the world's own recent output: what AFAR itself shipped.
  BEAT_RECEPTION — the Listener's logged reactions; the loop closing at set
                   boundaries (the fan's word reaches the next brief, never
                   a player's ear).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Sequence

from ensemble.ledger import Fragment
from ensemble.perceive import Evidence, Perceiver

BEAT_FIELD = "field-discourse"
BEAT_OWN = "own-output"
BEAT_RECEPTION = "reception"

# The broad-scan surfaces — the field the Muse covers. Where music is moving:
# releases and the argument around them, scenes, the AI-music culture AFAR is
# itself part of, and the industry weather. Dates are injected by the
# framework at runtime ({month_year}), never remembered.
BROAD_QUERIES: tuple[str, ...] = (
    "new album release most discussed {month_year}",
    "underground music scene sound trend {month_year}",
    "AI generated music culture argument {month_year}",
    "music industry streaming shift {month_year}",
)


@dataclass
class ProvenanceLog:
    """Accumulates the scan's evidence trail; the staff pass logs it as the
    brief row's `sources` so recency and sourcing stay auditable."""

    rows: list[dict] = field(default_factory=list)

    def record(self, cycle_id: str, evidence: Evidence, claim: str | None = None) -> None:
        self.rows.append(
            {
                "cycle": cycle_id,
                "title": evidence.title,
                "url": evidence.url,
                "published": evidence.published,
                "fetched_at": evidence.fetched_at,
                "source": evidence.source,
                "supports": claim,
            }
        )

    def to_json(self) -> str:
        return json.dumps({"evidence": self.rows}, indent=1) + "\n"


def evidence_to_fragment(e: Evidence) -> Fragment:
    """A broad-scan candidate becomes a dated ledger fragment (field beat).
    The URL rides in metadata as provenance; the content is the observation."""
    return Fragment(
        id=f"perceive-{abs(hash(e.url)) % 10**8}",
        content=f"{e.title}. {e.summary} ({e.url})",
        beat=BEAT_FIELD,
        author="muse-broad-scan",
        created_at=e.published,
        metadata={"subject": e.title, "url": e.url, "published": e.published},
    )


class MockSearch:
    """Offline adapter: three seeded music-field stories, dated inside the
    window relative to the injected clock, so the whole Muse pass runs (and
    precipitates a theme) with no network. Proves plumbing, not perception."""

    name = "mock-search"

    def search(self, query: str, *, now: date) -> Sequence[Evidence]:
        recent = (now - timedelta(days=8)).isoformat()
        older = (now - timedelta(days=21)).isoformat()
        return [
            Evidence(
                title="the year of the quiet record",
                url="https://example.com/field/quiet-records",
                published=recent,
                summary="A run of sparse, close-mic'd records is dominating the "
                "conversation; critics keep using the word 'unfinished' as praise. "
                "Quiet records, quiet rooms, quiet arguments about both.",
                source=self.name,
                fetched_at=now.isoformat(),
            ),
            Evidence(
                title="AI acts charting under house names",
                url="https://example.com/field/ai-house-names",
                published=recent,
                summary="Several AI acts are charting under invented band names and "
                "nobody involved will say who runs them. The argument is about "
                "disclosure, not quality — the records themselves are quiet hits.",
                source=self.name,
                fetched_at=now.isoformat(),
            ),
            Evidence(
                title="tape revival third wave",
                url="https://example.com/field/tape-revival",
                published=older,
                summary="Another tape revival, this one led by artists who never "
                "owned tape: hiss and wow as a texture choice, quiet fidelity as "
                "an aesthetic position rather than a constraint.",
                source=self.name,
                fetched_at=now.isoformat(),
            ),
        ]


def build_perceiver(
    model_live: bool, provider, sink: ProvenanceLog, *, window_days: int = 30
) -> Perceiver:
    """Live -> Anthropic web_search; offline -> canned mock. Swappable seam,
    same wiring as mold's build_perceiver."""
    if model_live:
        from ensemble.adapters.search import AnthropicWebSearch

        adapters = [AnthropicWebSearch(provider)]
    else:
        adapters = [MockSearch()]
    return Perceiver(adapters, window_days=window_days, sink=sink)
