"""The schedule: AFAR's nested clocks. Pure, deterministic, seedable, no I/O.

Three clocks, one inside the next: an ERA (the Muse's stance toward the
outside world holds for a whole era) contains SETS (one recording session
each — the conductor plays them back to back) contain ROUNDS (the players'
turns; `run_set` owns that innermost clock). This module only *plans*: it
answers "what is set N?" — condition, round count, stance, seed — without
ever touching a network, a filesystem, or a wall clock, so the conductor can
be restarted anywhere and replan the exact same future from the same seed.

Determinism is position-stable, the `player_seed` pattern: every set's plan
is derived from (schedule seed, set index) by hash offset, never from
iterator state — asking for set 40 first and set 3 later gives the same two
plans as walking 0..40 in order.

Era boundaries are the only place the world's slow state moves (DECISIONS.md
boundary rule, one level up): `should_roll_taboo` / `should_drift_persona`
are True exactly on the frame between two eras — the moment the
FieldTabooMemory rolls over and a persona is allowed to drift — and False
everywhere else, including set 0 (there is no boundary before the first era).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Iterator

#: The draw order for `condition_bias` — contact : isolation : parallel.
CONDITION_ORDER: tuple[str, str, str] = ("contact", "isolation", "parallel")


@dataclass(frozen=True)
class ScheduleConfig:
    """The authored knobs of the clocks. Everything else is derived.

    `condition_bias` weights the per-set condition draw (contact-heavy by
    default: the piece is about hearing each other, isolation and parallel
    are the controls). `rounds_per_set` is an inclusive range.
    `eras_stance_cycle` is authored, not drawn — the Muse's stance toward the
    outside world walks porous -> hostile -> oblivious and wraps.
    """

    condition_bias: tuple[int, int, int] = (3, 1, 1)
    rounds_per_set: tuple[int, int] = (5, 12)
    eras_stance_cycle: tuple[str, ...] = ("porous", "hostile", "oblivious")
    sets_per_era: int = 6
    seed: int = 0

    def __post_init__(self) -> None:
        lo, hi = self.rounds_per_set
        if lo < 1 or hi < lo:
            raise ValueError(f"rounds_per_set must be 1 <= lo <= hi, got {self.rounds_per_set}")
        if self.sets_per_era < 1:
            raise ValueError("sets_per_era must be >= 1")
        if not self.eras_stance_cycle:
            raise ValueError("eras_stance_cycle must not be empty")
        if len(self.condition_bias) != len(CONDITION_ORDER) or any(w < 0 for w in self.condition_bias):
            raise ValueError(f"condition_bias wants 3 non-negative weights, got {self.condition_bias}")
        if sum(self.condition_bias) == 0:
            raise ValueError("condition_bias must have at least one positive weight")


@dataclass(frozen=True)
class SetPlan:
    """One planned set: everything the conductor hands to run_set + the staff."""

    index: int  # global set index, 0-based
    era: int
    index_in_era: int
    era_stance: str
    condition: str
    rounds: int
    seed: int  # the set seed for run_set — derived, position-stable


@dataclass(frozen=True)
class EraPlan:
    """One planned era: its stance and its sets, in order."""

    index: int
    stance: str
    sets: tuple[SetPlan, ...]


def _derived_seed(seed: int, label: str) -> int:
    """Hash-offset derivation (the run.player_seed pattern): stable per label,
    no collisions when indices grow, independent of call order."""
    offset = int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16)
    return seed + offset


class Schedule:
    """The planner over one ScheduleConfig. Stateless: every method is a pure
    function of (config, arguments) — two Schedules with the same config agree
    about everything forever."""

    def __init__(self, config: ScheduleConfig | None = None) -> None:
        self.config = config or ScheduleConfig()

    # -- the era clock ---------------------------------------------------------

    def stance_for_era(self, era: int) -> str:
        cycle = self.config.eras_stance_cycle
        return cycle[era % len(cycle)]

    def era_of(self, set_index: int) -> int:
        return set_index // self.config.sets_per_era

    def eras(self) -> Iterator[EraPlan]:
        """Endless eras, each carrying its authored stance and planned sets."""
        era = 0
        while True:
            first = era * self.config.sets_per_era
            yield EraPlan(
                index=era,
                stance=self.stance_for_era(era),
                sets=tuple(self.set_plan(first + k) for k in range(self.config.sets_per_era)),
            )
            era += 1

    # -- the set clock ---------------------------------------------------------

    def next_condition(self, rng: random.Random) -> str:
        """One weighted condition draw (contact : isolation : parallel)."""
        weights = self.config.condition_bias
        pick = rng.randrange(sum(weights))
        for condition, weight in zip(CONDITION_ORDER, weights):
            if pick < weight:
                return condition
            pick -= weight
        raise AssertionError("unreachable: bias weights exhausted")

    def set_plan(self, set_index: int) -> SetPlan:
        """Plan one set from its global index alone. Position-stable: the rng
        is seeded per index, so the plan never depends on what was asked
        before it."""
        if set_index < 0:
            raise ValueError("set_index must be >= 0")
        rng = random.Random(_derived_seed(self.config.seed, f"set:{set_index}"))
        lo, hi = self.config.rounds_per_set
        era = self.era_of(set_index)
        return SetPlan(
            index=set_index,
            era=era,
            index_in_era=set_index % self.config.sets_per_era,
            era_stance=self.stance_for_era(era),
            condition=self.next_condition(rng),
            rounds=rng.randint(lo, hi),
            seed=_derived_seed(self.config.seed, f"set-seed:{set_index}"),
        )

    def sets(self) -> Iterator[SetPlan]:
        """Endless sets, in playing order."""
        index = 0
        while True:
            yield self.set_plan(index)
            index += 1

    # -- the era boundary: the only place slow state moves ---------------------

    def is_era_boundary(self, set_index: int) -> bool:
        """True on the frame BEFORE `set_index` — i.e. set_index opens a new
        era and an era just closed. Set 0 opens the first era; nothing closed,
        nothing rolls."""
        return set_index > 0 and set_index % self.config.sets_per_era == 0

    def should_roll_taboo(self, set_index: int) -> bool:
        """The FieldTabooMemory rolls over only between eras."""
        return self.is_era_boundary(set_index)

    def should_drift_persona(self, set_index: int) -> bool:
        """Persona drift is an era-boundary event, never a set-boundary one."""
        return self.is_era_boundary(set_index)
