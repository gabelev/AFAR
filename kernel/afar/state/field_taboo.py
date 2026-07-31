"""FieldTabooMemory: under a hostile era, the FIELD's moves are the taboo.

ensemble's TabooMemory forbids an agent's OWN last-cycle moves — the
anti-repetition store. AFAR's Muse needs the same mechanism pointed outward:
in a HOSTILE era the moves the outside world is making (the trends the
broad scan saw) are exactly what the acts must not do — hostility here is an
aesthetic stance, "whatever the field is doing, we are not." In porous and
oblivious eras the Muse still *observes* the field's moves (observation is
free), but nothing becomes forbidden from them.

The clock is the era (afar.schedule): `roll_over(stance)` is called only when
`Schedule.should_roll_taboo` says an era just closed. A hostile era's observed
field moves carry forward as the next era's inherited forbidden set — the
grudge outlives the stance by exactly one era, the same one-cycle horizon as
the base class. Any other stance rolls over clean.
"""

from __future__ import annotations

from ensemble.state.taboo import Move, TabooMemory

#: The stance under which observed field moves are forbidden.
HOSTILE = "hostile"


def field_move(subject: str) -> Move:
    """A field move as the Muse records one: the subject line of a piece of
    evidence, normalized so the same trend seen twice matches itself."""
    return Move(kind="field-move", signature=" ".join(subject.lower().split()))


class FieldTabooMemory(TabooMemory):
    """TabooMemory whose cycle is the ERA and whose moves belong to the field.

    `observe()` records what the broad scan saw this era. Under a hostile
    stance those moves are forbidden IMMEDIATELY — the era is hostile now,
    not next era — on top of whatever the previous era rolled in.
    """

    def __init__(self, stance: str = "porous", forbidden: tuple[Move, ...] | list[Move] = ()) -> None:
        super().__init__(forbidden)
        self.stance = stance

    # -- observing the field ---------------------------------------------------

    def observe(self, move: Move) -> None:
        """Record one field move seen this era (any stance; only hostile bites)."""
        self.record(move)

    def is_forbidden(self, move: Move) -> bool:
        if self.stance == HOSTILE and move.signature in {
            m.signature for m in self.used_this_cycle
        }:
            return True
        return super().is_forbidden(move)

    def forbidden_now(self) -> tuple[str, ...]:
        """Every signature currently off-limits — what the brief lists as
        forbidden moves. Inherited set always; this era's observations only
        under hostility."""
        inherited = self.forbidden_signatures
        if self.stance == HOSTILE:
            observed = {m.signature for m in self.used_this_cycle}
            return tuple(sorted(inherited | observed))
        return tuple(sorted(inherited))

    # -- the era boundary ------------------------------------------------------

    def roll_over(self, stance: str = "porous") -> "FieldTabooMemory":  # type: ignore[override]
        """Close the era; open the next one under `stance`.

        A hostile era's observations become the next era's inherited forbidden
        set (the base-class one-cycle horizon); any other era forbids nothing
        forward. Call only at era boundaries — Schedule.should_roll_taboo is
        the clock.
        """
        carried = list(self.used_this_cycle) if self.stance == HOSTILE else []
        return FieldTabooMemory(stance=stance, forbidden=carried)
