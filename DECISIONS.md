# DECISIONS

Architecture and art-direction decisions, newest first. Each entry: what was decided, why, and what it supersedes. The Notion "afar — MAS Design Brief" is the founding spec; entries here marked **override** take precedence over it.

## 2026-07-31

- **Naming register:** staff/press prose uses surnames (Marlowe / Patina / Lane); the acts use first names for each other in rationales. *(PR #7.)*
- **Per-act accent tones** scoped via `data-act` CSS custom-property override: silt keeps the house ochre; rust `#94512e`; keep `#5f7261`. The Radar silhouette in a framed "specimen plate" is each act's portrait until AI portraits land. *(PR #7.)*
- **Each personality is its own band.** Delta Marlowe, Roan Patina, and Evers Lane are three independent acts; **AFAR is the label/scene around them**, not a band name. The staff (Muse/Producer/Critic/Listener) are the label's masthead. The acts still perceive and influence each other — three acts on one label responding to each other's work. *(Override of the spec's "band" framing — Gabe.)*
- **Album covers are AI-image covers** (Tunz-style, prompt-driven from era + palette + visualStyle). *(Override of the spec §2 "the cover is the drawn interaction record / no image model in the loop" conceit — Gabe. The interaction record remains a first-class release artifact on the page; it's no longer the cover itself.)*
- **Stage names are display-only.** silt → Delta Marlowe, rust → Roan Patina, keep → Evers Lane. Entity IDs, URLs (`/agent/silt`), log keys, and DB keys never change — the display name is a presentation layer. Mineral slugs remain visible as sub-identities.
- **Lyrics are a dedicated Intent field.** `intent.lyrics` (model-written from `lyricalObsessions`, multi-line, ~1.5 words/sec per afar_music's PR #12 finding) is what gets sung; `line` is only the chat-bubble narration; `rationale` only the page text. First generation batch sang the narration line and came out effectively instrumental — that's why.

## 2026-07-30

- **Monorepo.** Kernel (Python) and web (Next.js) both live in `gabelev/AFAR` (`kernel/` + `web/`). *(Supersedes the spec §7 note that the web layer stays in its own repo.)*
- **License: AGPL-3.0-or-later** (was MIT at repo creation) — matches the `ensemble` framework's deliberate network-clause intent for hosted autonomous services.
- **Naming resolution** (spec §10 open decision, closed): `ensemble` = framework; **AFAR** = this installation, public face afar.band; `afar_music` = the separate product, afar.music; "The Ensemble Effect" = the offline research project, not a repo.
- **Renderer: ElevenLabs `music_v2` first, behind a swappable `Renderer` protocol.** `continue_from` is in the signature but raises on ElevenLabs (never use `conditioning_ref` for continuity — verified to produce near-covers). `MusicPromptError` is never auto-retried; only transient 429 retries once. 2-slot concurrency semaphore (process-local; needs a cluster lease before multi-process Step C).
- **Python/TS mapping parity is oracle-enforced.** `kernel/afar/mapping.py` must pass the oracles ported from `afar_music/lib/generation/mapping.test.ts`. JS `Math.round` ≠ Python `round` (banker's): all rounding goes through `_js_round(x) = floor(x + 0.5)`.
- **Append-only JSONL is authoritative; Neon is a derived mirror.** Every row carries condition, code_sha, seed, renderer_version, prompt_sha. Perceptions log what the agent *saw*. Artifacts are content-addressed and immutable. Embeddings are derived and carry model_id. *(The spec's earlier byte-identical-replay gate is cut — the experiment runs separately — but these provenance invariants survive it.)*
- **The site renders with zero env.** `web/lib/data.ts` falls back to bundled fixtures when `DATABASE_URL` is unset or any query fails. A broken DB degrades the site to fixtures; it never breaks a page.
- **Audio bytes live in Neon `media` (BYTEA), streamed via `/api/media/[id]`.** Not Vercel Blob (inherited decision from afar_music, where the linked Blob store was private). The `blob_url` pointer indirection keeps the byte store swappable.
- **Vercel:** Root Directory = `web`; framework pinned to `nextjs` in `web/vercel.json` (the dashboard preset was "Other", which made Vercel expect a static `public/` dir — first two deploys failed on these two settings).
- **MERT persona-distinctness gate runs at threshold 0.90, purity w.r.t. act identity.** The spec said 0.85, but mold's FMA bench shows 0.85 only separated Folk; clean separation needed ≥0.90. Do not weaken the threshold to pass — a failure is a persona-prompt problem.
- **Intent-space features are versioned.** `intent_vector` (18-dim: era/10 + 7 sonic + 2 vocal + 8 hashed-genre buckets) is pinned as `INTENT_VECTOR_VERSION = "1"`; embeddings rows carry the version so features stay comparable across runs.
- **Personas are defined by aesthetic commitment only** (accumulation / erosion / continuity), never by their relationship to influence — influence behaviour must emerge. *(Spec §2 trap, adopted as law.)*
- **The boundary rule is a single chokepoint.** `build_context()` is the only place condition branches; staff act between sets on the frame; within a set players perceive only players. The world enters through the brief, never the ear.
