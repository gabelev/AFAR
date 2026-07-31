# CLAUDE.md — AFAR

The build brief lives in Notion: "afar — MAS Design Brief". **DECISIONS.md in this repo records every decision since — where they conflict, DECISIONS.md wins.** When you make or receive a non-obvious decision (architecture or art direction), append it to DECISIONS.md in the same PR.

Key overrides already in effect: each personality is its own band/act (AFAR is the label, not a band); album covers are AI-image covers; players carry display-only stage names (Delta Marlowe/Roan Patina/Evers Lane) over stable IDs (silt/rust/keep).

## Naming — do not confuse these

- `ensemble` = the framework (Python package, imported here as an editable path dep). Lives at `../moldzine/ensemble` locally.
- **AFAR (this repo)** = the installation / live art piece. Public face **afar.band**. Python package name: `afar`.
- `afar_music` = a *different* repo: the AI-artist product (`../ai-music/afar_music`), public face afar.music. We port code *from* it; we never modify it from here.
- "The Ensemble Effect" = the research project (offline experiment), not a repo.

## Architecture rules (load-bearing — violations poison the data)

1. **The boundary rule.** Staff (Muse/Producer/Critic/Listener) act on the *frame* between sets. Players act on *each other* within a set. A player's perceive context contains ONLY other players' material, mid-set. The loop closes at set boundaries, never round boundaries. `build_context()` in `kernel/afar/perception/context.py` is the single chokepoint.
2. **The world enters through the brief, never the ear.** Field audio/discourse reaches players only via the Muse → Producer brief at set start.
3. **Append-only log is authoritative.** JSONL under `runs/` is the source of truth; Neon is a derived mirror. Never edit logged rows. Artifacts are content-addressed and immutable.
4. **Personas are defined by aesthetic commitment, never by their relationship to influence.** (No "the mimic", no "the refuser".) Influence behaviour must emerge.
5. **The cover is a function, not an agent.** Deterministic render of the interaction record.
6. **Copyright discipline lives in the embedder path**: external audio is read transiently, features persisted, waveforms discarded.

## Kernel conventions

- Python ≥3.11, `uv`. Run tests: `cd kernel && uv run pytest`. All tests offline (Mock{Provider,Renderer,Embedder}); anything hitting a real API is a manual script, not a test.
- `ensemble` import quirks: `Agent.run()` does NOT call `publish()` — orchestrators log explicitly. Import `Agent/Persona/SelfState` from `ensemble.agent`; `AnthropicProvider` from `ensemble.providers.anthropic`.
- **JS parity:** `kernel/afar/mapping.py` must match `afar_music/lib/generation/mapping.test.ts` oracles. JS `Math.round` ≠ Python `round` — use `_js_round(x) = floor(x + 0.5)`.
- ElevenLabs `music_v2`: 2-concurrent max, 90s timeout, metadata on `x-*` response headers, `MusicPromptError` is never auto-retried (surface `.suggestion`), never use `conditioning_ref` for continuity.
- Stable public entity IDs: `agent:{silt,rust,keep,muse,producer,critic,listener}`, `release:{NNNN}`; artifacts by content hash. These join the log, the URLs, and the world renderer — never rename.

## Web conventions

- `web/` is adapted from `afar_music` (studio stripped). It only READS. No generation code in web/.
- Renders from `web/fixtures/` when `DATABASE_URL` is unset — keep every page working with zero env.
- Audio authority: exactly one `<audio>` owner; the world renderer never originates sound.

## Deploys

Vercel is linked to this repo, Root Directory = `web`. Push to `main` deploys production. Kernel never runs on Vercel.
