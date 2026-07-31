"""Player: one AFAR musician running PERCEIVE -> DECIDE -> EXECUTE.

A Player is an ensemble Agent whose decision is an `Intent` (the Creative DNA
plus a spoken line) and whose execution is a rendered track on disk. The model
never touches the renderer and the renderer never touches the model: the
Intent is the only thing that crosses between them, which is what makes every
track reproducible from its logged intent.

`ensemble.agent.Agent.run()` deliberately does NOT publish or log — so the
logging lives in `render_one`, the Step A orchestrator, which runs the loop
stage by stage and writes the perceptions/intents/artifacts rows explicitly.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from ensemble.agent import Agent, Artifact, Decision, Perception, Persona, SelfState
from ensemble.memory import EpisodicMemory
from ensemble.providers.model import Message, ModelProvider

from afar.intent import Intent
from afar.log import JsonlLedger
from afar.render.base import DEFAULT_DURATION_S, Renderer


class Player(Agent):
    """A persona + model + renderer, closing the loop from hearing to track."""

    def __init__(
        self,
        persona: Persona,
        model: ModelProvider,
        renderer: Renderer,
        *,
        self_state: Optional[SelfState] = None,
        memory: Optional[EpisodicMemory] = None,
    ) -> None:
        super().__init__(persona, model, self_state=self_state, memory=memory)
        self.renderer = renderer
        # The seed for the NEXT render. Set by the orchestrator per round;
        # execute() only receives a Decision, so the seed rides on the player.
        self.seed: int = 0
        # The take length for the NEXT render (the Producer's session length).
        # Set by the orchestrator per set — same pattern as `seed`.
        self.duration_s: int = DEFAULT_DURATION_S

    # -- PERCEIVE --------------------------------------------------------------

    def perceive(self, context: Mapping[str, Any]) -> Perception:
        """Wrap the given context untouched.

        The boundary rule (what a player may hear mid-set: ONLY other players'
        material) is enforced where the context is BUILT, not here — a player
        never second-guesses its own ears.
        """
        return Perception(data=dict(context))

    # -- DECIDE ----------------------------------------------------------------

    def decide(self, perception: Perception) -> Decision:
        """Ask the model for an Intent; one re-prompt on a malformed reply.

        One retry, not more: a model that cannot produce a valid intent twice
        in a row is a bug to surface, not noise to smooth over — silently
        looping would hide broken personas from the log.
        """
        messages = [
            Message(role="system", content=self.persona.base_prompt),
            Message(role="user", content=self._decision_prompt(perception)),
        ]
        raw = self.model.complete(messages)
        try:
            intent = Intent.from_json(raw)
        except ValueError as err:
            retry = messages + [
                Message(role="assistant", content=raw),
                Message(
                    role="user",
                    content=(
                        f"That reply was not a valid Intent ({err}). "
                        "Reply again with ONLY the corrected JSON object."
                    ),
                ),
            ]
            intent = Intent.from_json(self.model.complete(retry))  # raises if still bad
        return Decision(data={"intent": intent})

    # -- EXECUTE ---------------------------------------------------------------

    def execute(self, decision: Decision) -> Artifact:
        intent: Intent = decision.data["intent"]
        result = self.renderer.render(intent, seed=self.seed, duration_s=self.duration_s)
        return Artifact(
            kind="track",
            body=str(result.path),
            metadata={
                "intent": intent.to_dna_dict(),
                "line": intent.line,
                "lyrics": intent.lyrics,
                "rationale": intent.rationale,
                "content_hash": result.content_hash,
                "prompt_sha": result.prompt_sha,
                "renderer_version": result.renderer_version,
                "render": dict(result.metadata),
            },
        )

    # -- internals -------------------------------------------------------------

    def _decision_prompt(self, perception: Perception) -> str:
        """The decide-turn user message: the Producer's direction (frame, when
        the set has one), the player's own drifted self-state, what the other
        takes measurably SOUNDED like, then the room.

        The direction is rendered apart from the peer material on purpose —
        it is the frame the session happens inside, not something another act
        played. The self-state line comes from the player itself (SelfState is
        the player's own residue, never part of the built context). The heard
        facts are rendered as their own plain-language block and stripped from
        the room's JSON dump — one fact, said once; the LOGGED context still
        carries the full heard dict, because the log records what was built,
        not how the prompt phrased it."""
        data = dict(perception.data)
        direction = data.pop("direction", None)
        heard_block = self._extract_heard(data)
        parts: list[str] = []
        if direction:
            parts.append(_render_direction(direction))
        state_line = self._self_state_line()
        if state_line:
            parts.append(state_line)
        if heard_block:
            parts.append(heard_block)
        if not data:
            parts.append(
                "The room is empty — no one has played yet. You open the set. "
                "Reply with your Intent JSON."
            )
        else:
            parts.append(
                "What you can hear right now (the other players' material):\n"
                + json.dumps(data, indent=2, default=str)
                + "\n\nMake your track. Reply with your Intent JSON."
            )
        return "\n\n".join(parts)

    def _extract_heard(self, data: dict[str, Any]) -> Optional[str]:
        """Pop each other-act entry's `heard` dict out of `data` (in place)
        and render the WHAT YOU HEARD block, or None when nothing was heard.

        First names come from the persona's addresses map — the block speaks
        the way the room does. Own take carries no heard facts by design (the
        act made it), so this only ever describes the others."""
        others = data.get("others")
        if not others:
            return None
        addresses: Mapping[str, str] = self.persona.metadata.get("addresses", {})
        lines: list[str] = []
        stripped: list[dict[str, Any]] = []
        for entry in others:
            entry = dict(entry)
            heard = entry.pop("heard", None)
            stripped.append(entry)
            if heard:
                pid = str(entry.get("player_id", ""))
                sentence = _heard_sentence(addresses.get(pid, pid), heard)
                if sentence:
                    lines.append(sentence)
        data["others"] = stripped
        if not lines:
            return None
        return (
            "WHAT YOU HEARD (measured from the audio of their last takes):\n"
            + "\n".join(lines)
        )

    def _self_state_line(self) -> Optional[str]:
        """One line of who-you-have-become, present only once drift exists:
        'Era N, stance S. You keep returning to: ...' — the logged
        persona_state rows made behavioral, still fully auditable."""
        state = self.self_state
        residue = dict(state.residue or {})
        obsessions = [str(o).strip() for o in (state.obsessions or []) if str(o).strip()]
        bits: list[str] = []
        era, stance = residue.get("era"), residue.get("stance")
        if era is not None and stance:
            bits.append(f"Era {era}, stance {stance}.")
        elif stance:
            bits.append(f"Stance {stance}.")
        if obsessions:
            bits.append("You keep returning to: " + ", ".join(obsessions) + ".")
        if not bits:
            return None
        return "WHERE YOU ARE NOW: " + " ".join(bits)


def _heard_sentence(name: str, heard: Mapping[str, Any]) -> Optional[str]:
    """One act's heard dict as one terse studio sentence, e.g.
    "Roan's last take: about 98 BPM, quiet, dark, 60 seconds. It moved away
    from yours — closer to their own last one."

    Facts only, no adjectives beyond the measured buckets; whatever was not
    measured is simply not said. Returns None when there is nothing to say
    (fully degraded DSP and no movement to report)."""
    facts: list[str] = []
    if heard.get("tempo_bpm") is not None:
        facts.append(f"about {round(float(heard['tempo_bpm']))} BPM")
    if heard.get("loudness"):
        label = str(heard["loudness"])
        facts.append(label if label != "mid" else "mid loudness")
    if heard.get("brightness"):
        label = str(heard["brightness"])
        facts.append(label if label != "mid" else "mid brightness")
    if heard.get("duration_s") is not None:
        facts.append(f"{round(float(heard['duration_s']))} seconds")
    moved = heard.get("moved")
    tail: Optional[str] = None
    if moved == "toward_you":
        tail = "It moved toward yours — away from their own last one."
    elif moved == "away_from_you":
        tail = "It moved away from yours — closer to their own last one."
    if not facts and not tail:
        return None
    sentence = f"{name}'s last take:"
    if facts:
        sentence += " " + ", ".join(facts) + "."
    if tail:
        sentence += f" {tail}"
    return sentence


def _render_direction(direction: Mapping[str, Any]) -> str:
    """The Producer's session frame, rendered as prose the act reads before
    the room. Only the whitelisted frame fields ever reach this (see
    afar.perception.context.direction_frame)."""
    lines = ["THE PRODUCER'S DIRECTION FOR THIS SESSION:"]
    text = str(direction.get("text", "")).strip()
    if text:
        lines.append(text)
    notes = [str(n).strip() for n in direction.get("palette_notes", ()) if str(n).strip()]
    if notes:
        lines.append("Palette notes: " + "; ".join(notes))
    forbidden = [str(m).strip() for m in direction.get("forbidden_moves", ()) if str(m).strip()]
    if forbidden:
        lines.append("Off the table this session: " + "; ".join(forbidden))
    duration = direction.get("duration_s")
    if duration:
        lines.append(
            f"Take length this session: {int(duration)} seconds — "
            "size your lyrics to fill it."
        )
    return "\n".join(lines)


def render_one(
    player: Player,
    context: Mapping[str, Any],
    ledger: JsonlLedger,
    *,
    seed: int,
    condition: str,
) -> Artifact:
    """One player, one round: run the PDE loop and log every stage.

    This exists because Agent.run() returns only the final artifact and never
    publishes — but the log needs the intermediate facts (what was heard, what
    was intended) as first-class rows. Rows are written after EXECUTE so all
    three carry the full provenance stamp (renderer_version and prompt_sha are
    only known once the render request exists).
    """
    perception = player.perceive(context)
    decision = player.decide(perception)
    intent: Intent = decision.data["intent"]

    player.seed = seed
    artifact = player.execute(decision)

    stamps = {
        "condition": condition,
        "seed": seed,
        "renderer_version": artifact.metadata["renderer_version"],
        "prompt_sha": artifact.metadata["prompt_sha"],
    }
    intent_id = intent.content_hash()
    ledger.write(
        "perceptions",
        {**stamps, "player": intent.player_id, "context": dict(perception.data)},
    )
    ledger.write(
        "intents",
        {
            **stamps,
            "id": intent_id,
            "player": intent.player_id,
            "intent": intent.to_dna_dict(),
            "line": intent.line,
            "lyrics": intent.lyrics,
            "rationale": intent.rationale,
        },
    )
    # Content-addressed: the row's id IS the file's sha256. Path + hash only —
    # bytes live on disk, never in the log.
    ledger.write(
        "artifacts",
        {
            **stamps,
            "id": artifact.metadata["content_hash"],
            "kind": artifact.kind,
            "player": intent.player_id,
            "path": artifact.body,
            "hash": artifact.metadata["content_hash"],
            "intent_id": intent_id,
        },
    )
    player.memory.remember({"persona": player.persona.name, "artifact_kind": artifact.kind})
    return artifact
