"""The Muse: the brief precipitates; failure thins it; hostility forbids.

Offline end to end (MockProvider + MockSearch). Under test: the theme coming
from the densest cluster across discourse + own output + reception, the
never-stops rule (a raising adapter yields a thinner brief, not an error),
the FieldTabooMemory stance mechanics and era rollover, and the boundary
seam — the brief is consumed by the Producer's direction half, and nothing
brief-shaped exists in a player's mid-set context builder.
"""

from __future__ import annotations

from datetime import date

import pytest
from ensemble.perceive import Perceiver
from ensemble.providers.model import MockProvider

from afar.agents.muse import MuseAgent, STANCES
from afar.agents.producer import ProducerAgent
from afar.config import _mock_players
from afar.perception.field import MockSearch, ProvenanceLog, build_perceiver
from afar.state.field_taboo import FieldTabooMemory, field_move

_TODAY = date(2026, 7, 31)

#: A minimal staff-cut release record — what a Muse reads after a set ships.
_RECORD = {
    "release_id": "aaaa1111bbbb2222",
    "set": {"condition": "contact", "rounds": 2, "players": ["silt", "rust", "keep"], "seed": 7},
    "rounds": [
        {
            "silt": {"line": "laying a floor first", "lyrics": "lay it down\nthe room is filling in"},
            "rust": {"line": "kept the hiss", "lyrics": "the tape wore through your name"},
            "keep": {"line": "four chords, played plain", "lyrics": "same four chords, same open door"},
        },
        {
            "silt": {"line": "buried the hook alive", "lyrics": "silt over silt over song"},
            "rust": {"line": "cut the second bar", "lyrics": "half the chord is missing"},
            "keep": {"line": "back to the top", "lyrics": "we always come back"},
        },
    ],
    "artifacts": [{"silt": "s0", "rust": "r0", "keep": "k0"}, {"silt": "s1", "rust": "r1", "keep": "k1"}],
    "staff": {
        "producer": {
            "selected": {
                "silt": {"round": 1, "take_id": "s1"},
                "rust": {"round": 0, "take_id": "r0"},
                "keep": {"round": 1, "take_id": "k1"},
            },
            "note": "One take from each act.",
        },
        "critic": {
            "release_title": "Quiet Rooms",
            "take_titles": {"silt": "Buried Alive", "rust": "The Hiss", "keep": "Back To The Top"},
            "release_review": "Quiet, again.",
            "act_reviews": {"silt": "Marlowe stacked.", "rust": "Patina cut.", "keep": "Lane returned."},
        },
    },
}

_STAGE_NAMES = {"silt": "Delta Marlowe", "rust": "Roan Patina", "keep": "Evers Lane"}


class _RaisingSearch:
    """An adapter that fails the way the outside world fails."""

    name = "raising-search"

    def search(self, query, *, now):
        raise ConnectionError("the field is unreachable")


def _muse(**kw) -> MuseAgent:
    defaults = dict(
        perceiver=Perceiver([MockSearch()], window_days=30, sink=None, clock=lambda: _TODAY),
        clock=lambda: _TODAY,
    )
    defaults.update(kw)
    return MuseAgent(MockProvider(responder=_mock_players), **defaults)


def _compose(muse: MuseAgent, *, stance: str = "porous", reactions=()):
    return muse.compose(
        stance=stance,
        release_records=[_RECORD],
        reaction_rows=list(reactions),
        stage_names=_STAGE_NAMES,
        carried_forward=True,
    )


# --- the brief precipitates ----------------------------------------------------


def test_brief_precipitates_a_theme_with_sources_and_prose():
    brief = _compose(_muse())
    assert brief.stance == "porous"
    assert brief.theme and brief.theme != "silence"
    assert brief.body and "[mock]" in brief.body  # public prose, model-written
    assert brief.palette_notes  # working notes ride along
    assert not brief.thin  # the scan came back
    assert brief.carried_forward is True
    # Discourse sources are auditable URLs. (MockSearch seeds "quiet" across
    # stories; the theme cluster sits on dated, sourced evidence.)
    assert all(url.startswith("https://") for url in brief.sources)


def test_theme_is_the_densest_cluster_across_all_beats():
    # MockSearch's three stories share the word "quiet" — the field keeps
    # reaching for it, so that is what precipitates. Nobody chose it.
    brief = _compose(_muse())
    assert brief.theme == "quiet"


def test_domain_trivial_words_cannot_be_the_theme():
    # In a world entirely about music, "music" as a theme says nothing — the
    # clusterer skips domain-trivial labels (first live scan precipitated
    # exactly this) and precipitates the next-densest informative cluster.
    from ensemble.ledger import Fragment

    from afar.agents.muse import FieldClusterer

    fragments = [
        Fragment(id=str(i), content=text, beat="field-discourse", author="t", created_at="2026-07-01")
        for i, text in enumerate(
            [
                "music streaming quiet shift july",
                "music industry quiet report july",
                "music culture argument july",
            ]
        )
    ]
    ranked = FieldClusterer().precipitate(fragments)
    # "music" and "july" (the injected query date) touched all three — both
    # are barred; the densest INFORMATIVE cluster precipitates instead.
    assert ranked[0].label == "quiet"


def test_reception_fragments_join_the_field():
    reactions = [
        {"kind": "reaction", "valence": "cold", "text": "meandering, honestly meandering", "ts": "2026-07-30T00:00:00"},
        {"kind": "reaction", "valence": "cold", "text": "still meandering", "ts": "2026-07-30T01:00:00"},
    ]
    provider = MockProvider(responder=_mock_players)
    muse = _muse()
    muse.model = provider
    _compose(muse, reactions=reactions)
    prompt = "\n".join(m.content for m in provider.calls[-1])
    assert "meandering, honestly meandering" in prompt  # the fan's word reached the brief


# --- external failure never stops anything -------------------------------------


def test_failed_scan_yields_a_thinner_brief_not_an_error():
    muse = _muse(perceiver=Perceiver([_RaisingSearch()], window_days=30, clock=lambda: _TODAY))
    brief = _compose(muse)
    assert brief.thin is True
    assert brief.sources == ()  # nothing sourced — and nothing claimed
    assert brief.theme  # …but a theme still precipitated from own output
    assert brief.body  # and the brief still shipped


def test_no_perceiver_at_all_still_briefs():
    brief = _compose(_muse(perceiver=None))
    assert brief.thin is True and brief.body


# --- hostility: the field's moves become forbidden ------------------------------


def test_hostile_stance_forbids_the_fields_moves():
    taboo = FieldTabooMemory(stance="hostile")
    brief = _compose(_muse(taboo=taboo), stance="hostile")
    assert brief.forbidden_moves  # the observed field moves are off-limits
    assert "the year of the quiet record" in brief.forbidden_moves
    assert taboo.is_forbidden(field_move("The Year of the QUIET record"))  # normalized match


def test_porous_stance_observes_but_forbids_nothing():
    taboo = FieldTabooMemory(stance="porous")
    brief = _compose(_muse(taboo=taboo), stance="porous")
    assert brief.forbidden_moves == ()
    assert not taboo.is_forbidden(field_move("the year of the quiet record"))
    assert taboo.used_this_cycle  # observation is free under any stance


def test_field_taboo_rolls_over_at_era_boundaries():
    hostile = FieldTabooMemory(stance="hostile")
    hostile.observe(field_move("tape revival third wave"))
    # A hostile era's grudge carries into the next era's inherited set…
    nxt = hostile.roll_over(stance="porous")
    assert nxt.stance == "porous"
    assert nxt.is_forbidden(field_move("tape revival third wave"))
    assert nxt.forbidden_now() == ("tape revival third wave",)
    # …and dies with THAT era: a non-hostile era forbids nothing forward.
    assert nxt.roll_over(stance="oblivious").forbidden_now() == ()


# --- the boundary rule ----------------------------------------------------------


def test_the_brief_is_consumed_by_the_producers_direction_half():
    brief = _compose(_muse())
    producer = ProducerAgent(MockProvider(responder=_mock_players))
    direction = producer.direct(brief)
    assert direction["stance"] == brief.stance
    assert direction["theme"] == brief.theme
    assert direction["text"] == brief.body
    assert direction["palette_notes"] == list(brief.palette_notes)
    assert direction["forbidden_moves"] == list(brief.forbidden_moves)


def test_nothing_brief_shaped_can_enter_a_mid_set_context():
    # build_context is the single chokepoint (rule 1) and its signature admits
    # players' RunView state only — there is no parameter a brief could ride
    # in on. The world enters through the brief at set start, never the ear.
    import inspect

    from afar.perception.context import build_context

    params = set(inspect.signature(build_context).parameters)
    assert params == {"player_id", "t", "run", "condition"}


# --- wiring ---------------------------------------------------------------------


def test_build_perceiver_offline_uses_the_mock_adapter():
    perceiver = build_perceiver(False, None, ProvenanceLog())
    assert isinstance(perceiver.adapters[0], MockSearch)


def test_every_schedule_stance_has_muse_vocabulary():
    from afar.schedule import ScheduleConfig

    for stance in ScheduleConfig().eras_stance_cycle:
        assert stance in STANCES
