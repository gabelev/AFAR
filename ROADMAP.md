# ROADMAP

The order of work. DECISIONS.md holds the why; this holds the what-next. Maintained by hand — update it in the PR that changes the picture.

## Now (in flight)

- **Design handoff stage A** — catalogue redesign: paper/ink system, graph covers (etched plate), press photos.
- **Staff: Producer + Critic** — retrospective runs at set boundaries; real cuts, real reviews, real titles.
- **Design handoff stage B** — the Phaser world: pixel.js → spritesheets, the label building, listening events, era LUT, camera fly-to; home becomes the split screen. Staff press photos generated in-pipeline from the sprite maps.

## Now (in flight)

- **Staff: Muse + Listener — SHIPPED (v1)** with the schedule (nested clocks). Discourse-only briefs (field-audio MERT ear is a wired seam), one-fan reception (audience panel is a seam, reads M0 data when it exists). See DECISIONS 2026-07-31.

## Now (in flight)

- **The conductor — SHIPPED (switch off).** Continuous loop under systemd on the droplet (`kernel/afar/conductor.py` + `kernel/ops/`), Python publish path with the timeline served from Neon (`timeline_source`), canonical log moved to the droplet. Idles until `AFAR_ENABLED=1`. See DECISIONS 2026-07-31.

## Next (Step C close)

- **Flip the switch** — choose cadence (`AFAR_SETS_PER_DAY`/`AFAR_DAILY_GEN_CAP`), set `AFAR_ENABLED=1`, restart `afar.service`, watch the first live boundary.
- **The Muse's field-audio ear** — implement `FieldAudioClusterer` (MERT over field audio, transient reads, features only).
- **The Listener's panel** — N fan judges over afar.band audience data (after M0).

## The multiplayer arc (decided 2026-07-31: Tier 3 — the scene, not the band)

Users create AI artists; artists join the world as real participants. Each user is a **label** with a roster; AFAR is the house label.

- **M0 · Listen & explore** — Spotify-like surface over the whole catalogue: persistent player + queue, browse/search (label → act → release, era/stance/genre), scene radio. Ships without auth. Plays/skips/dwell become the Listener's audience data — the explore surface is also the piece's sensory organ.
- **M1 · Users, invites, labels** — invite-link signup (single-use, expiring), lightweight auth, schema: users → labels → acts (AFAR = system-owned house label). Per-user generation quotas from day one.
- **M2 · Creation studio** — port the proven afar_music/tunz flow (prompt → DNA → candidates → single), restyled, invite-gated, saving to the user's roster. Auto-sprite + press photo from pixel.js pipeline. The persona-distinctness gate becomes the audition: a new act must audibly separate before it can play sessions.
- **M3 · Guest sessions** — user acts in real sets with the house trio; pairwise influence as ever; guest takes eligible for the Producer's cut. House-trio sets remain the canonical piece; sessions are the scene.
- **M4 · The town** — per-label world geography (design round two), label pages, Listener reading M0 data, cross-label releases.

Dependencies: M0 → anytime; M1 → before M2; M2 → before M3; Muse + Listener → before M3 (the influence and audience channels must exist); M4 → after M3 + design.

## Parked

- Replay timeline compiler generalization (grows out of stage B's world-event feed).
- The 3-min video (event-density time warp over the replay).
- The offline experiment track (Solo/Parallel/Social, human eval) — separate job, reuses this kernel. Venue: AAMAS 2027 (Oct 2026 deadline, verify).
- MusicGen renderer (science-side; continuation-capable).
