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
from afar.render.base import Renderer


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
        result = self.renderer.render(intent, seed=self.seed)
        return Artifact(
            kind="track",
            body=str(result.path),
            metadata={
                "intent": intent.to_dna_dict(),
                "line": intent.line,
                "rationale": intent.rationale,
                "content_hash": result.content_hash,
                "prompt_sha": result.prompt_sha,
                "renderer_version": result.renderer_version,
                "render": dict(result.metadata),
            },
        )

    # -- internals -------------------------------------------------------------

    @staticmethod
    def _decision_prompt(perception: Perception) -> str:
        if not perception.data:
            return (
                "The room is empty — no one has played yet. You open the set. "
                "Reply with your Intent JSON."
            )
        return (
            "What you can hear right now (the other players' material):\n"
            + json.dumps(perception.data, indent=2, default=str)
            + "\n\nMake your track. Reply with your Intent JSON."
        )


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
