"""The nested clocks: pure, deterministic, seedable. Same seed, same future."""

from __future__ import annotations

import random
from itertools import islice

import pytest

from afar.schedule import CONDITION_ORDER, Schedule, ScheduleConfig, SetPlan


def _plans(schedule: Schedule, n: int) -> list[SetPlan]:
    return list(islice(schedule.sets(), n))


# --- determinism ---------------------------------------------------------------


def test_same_seed_same_sequence():
    a = Schedule(ScheduleConfig(seed=42))
    b = Schedule(ScheduleConfig(seed=42))
    assert _plans(a, 40) == _plans(b, 40)
    # And re-walking the same instance replays the same future.
    assert _plans(a, 40) == _plans(a, 40)


def test_different_seed_different_sequence():
    a = _plans(Schedule(ScheduleConfig(seed=1)), 40)
    b = _plans(Schedule(ScheduleConfig(seed=2)), 40)
    assert a != b


def test_position_stable_plans_never_depend_on_call_order():
    # Asking for set 33 cold gives the same plan as walking there — a restarted
    # conductor replans the identical future.
    schedule = Schedule(ScheduleConfig(seed=7))
    cold = schedule.set_plan(33)
    walked = _plans(schedule, 40)[33]
    assert cold == walked
    # Set seeds are distinct per set (hash-offset derivation).
    seeds = [p.seed for p in _plans(schedule, 40)]
    assert len(set(seeds)) == len(seeds)


def test_negative_index_refused():
    with pytest.raises(ValueError):
        Schedule().set_plan(-1)


# --- the set clock -------------------------------------------------------------


def test_rounds_stay_inside_the_inclusive_range():
    config = ScheduleConfig(rounds_per_set=(5, 12), seed=3)
    rounds = [p.rounds for p in _plans(Schedule(config), 300)]
    assert all(5 <= r <= 12 for r in rounds)
    assert min(rounds) == 5 and max(rounds) == 12  # both bounds actually drawn


def test_condition_bias_weights_the_draw():
    # 3:1:1 over many sets: contact dominates, the controls stay comparable.
    plans = _plans(Schedule(ScheduleConfig(seed=11)), 600)
    counts = {c: sum(p.condition == c for p in plans) for c in CONDITION_ORDER}
    assert sum(counts.values()) == 600
    assert counts["contact"] > counts["isolation"] * 2
    assert counts["contact"] > counts["parallel"] * 2
    assert counts["isolation"] > 0 and counts["parallel"] > 0


def test_next_condition_honors_zero_weights():
    schedule = Schedule(ScheduleConfig(condition_bias=(0, 1, 0)))
    rng = random.Random(0)
    assert all(schedule.next_condition(rng) == "isolation" for _ in range(20))


# --- the era clock -------------------------------------------------------------


def test_stances_walk_the_authored_cycle_and_wrap():
    schedule = Schedule(ScheduleConfig(seed=0))
    stances = [era.stance for era in islice(schedule.eras(), 7)]
    assert stances == ["porous", "hostile", "oblivious", "porous", "hostile", "oblivious", "porous"]


def test_eras_nest_their_sets():
    schedule = Schedule(ScheduleConfig(sets_per_era=6, seed=5))
    eras = list(islice(schedule.eras(), 3))
    for era in eras:
        assert len(era.sets) == 6
        for k, plan in enumerate(era.sets):
            assert plan.index == era.index * 6 + k
            assert plan.index_in_era == k
            assert plan.era == era.index
            assert plan.era_stance == era.stance
    # The nested view and the flat view are the same clock.
    flat = _plans(schedule, 18)
    assert [p for era in eras for p in era.sets] == flat


def test_era_boundaries_are_the_only_place_slow_state_moves():
    schedule = Schedule(ScheduleConfig(sets_per_era=6))
    for fn in (schedule.should_roll_taboo, schedule.should_drift_persona):
        assert fn(0) is False  # nothing closed before the first era
        assert all(fn(i) is False for i in range(1, 6))
        assert fn(6) is True
        assert all(fn(i) is False for i in range(7, 12))
        assert fn(12) is True


# --- config validation ---------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rounds_per_set": (0, 4)},
        {"rounds_per_set": (8, 5)},
        {"sets_per_era": 0},
        {"eras_stance_cycle": ()},
        {"condition_bias": (1, 1)},
        {"condition_bias": (0, 0, 0)},
        {"condition_bias": (-1, 1, 1)},
    ],
)
def test_bad_config_refused(kwargs):
    with pytest.raises(ValueError):
        ScheduleConfig(**kwargs)
