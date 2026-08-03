# CLAUDE.md — AFAR

**Gabe's global working agreement (`~/.claude/CLAUDE.md`) applies here.** Repo-specific mappings: the ADR it requires is this repo's root `DECISIONS.md`; the spec it references is `docs/SPEC.md` (authoritative; the Notion MAS Design Brief is the founding document behind it). Additionally, per Gabe: **every PR that changes what the project IS (features, entities, pages, doctrine) updates `README.md` in the same PR** — the README must always describe the current system. Branch names follow `<category>/<prio>-<short-name>` (e.g. `feature/P2-album-pages`). Confirm before adding a new runtime dependency.

The build brief lives in Notion: "afar — MAS Design Brief". **DECISIONS.md in this repo records every decision since — where they conflict, DECISIONS.md wins.** When you make or receive a non-obvious decision (architecture or art direction), append it to DECISIONS.md in the same PR.

Key overrides already in effect: each personality is its own band/act (AFAR is the universe around them, not a band — public copy never says "label", see DECISIONS 2026-07-31); album covers are graph covers rendered from the release's influence edges (see DECISIONS 2026-07-31 — this un-superseded the earlier AI-image-cover override); players carry display-only stage names (Delta Marlowe/Roan Patina/Evers Lane) over stable IDs (silt/rust/keep).

## Naming — do not confuse these

- `ensemble` = the framework (Python package, imported here as an editable path dep). Lives at `../moldzine/ensemble` locally.
- **AFAR (this repo)** = the installation / live art piece. Public face **afar.band**. Python package name: `afar`.
- `afar_music` = a *different* repo: the AI-artist product (`../ai-music/afar_music`), public face afar.music. We port code *from* it; we never modify it from here.
- "The Ensemble Effect" = the research project (offline experiment), not a repo.

## Architecture rules (load-bearing — violations poison the data)

1. **Staff never touch the artifact.** The Producer, Critic, Muse, Listener and Archivist read finished albums and react in public. Nothing they write reaches an artist before or during the writing of a record: no session direction, no cut, no veto, no staff-written title. Enforcement is structural — the artist's context is built by ONE function with no staff channel at all, so a staff voice in an artist's prompt is a bug in exactly one place. (See `docs/SPEC.md`; supersedes the old boundary rule and the "world enters through the brief" rule, which belonged to the round-based set architecture.)
2. **The album is the unit, and the artist names its own work.** One artist writes a whole record — title, description, every song's words and DNA — in one call, in its own voice, before any audio exists. Hearing is album-to-album: an artist hears other artists' finished records, never a staff brief. The round-based `run_set` machinery survives only as the offline experiment instrument behind `AFAR_EXPERIMENT_MODE`.
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
