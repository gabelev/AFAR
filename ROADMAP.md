# ROADMAP

The order of work. DECISIONS.md holds the why; this holds the what-next. Maintained by hand — update it in the PR that changes the picture.

## Now (in flight)

- **Design handoff stage A** — catalogue redesign: paper/ink system, graph covers (etched plate), press photos.
- **Staff: Producer + Critic** — retrospective runs at set boundaries; real cuts, real reviews, real titles.
- **Design handoff stage B** — the Phaser world: pixel.js → spritesheets, the label building, listening events, era LUT, camera fly-to; home becomes the split screen. Staff press photos generated in-pipeline from the sprite maps.

## Next (Step C close)

- **The Muse** — field perception (discourse + audio), era stance (porous/hostile/oblivious), the brief. The world enters through the brief, never the ear.
- **The Listener** — reception + valence; consumes afar.band audience data when it exists (see M0).
- **The conductor** — continuous unattended running under systemd (droplet move at a set boundary; the JSONL log moves with it and the droplet becomes the only kernel writer).

## The multiplayer arc (decided 2026-07-31: Tier 3 — the scene, not the band)

Users create AI artists; artists join the world as real participants. Each user is a **label** with a roster; AFAR is the house label.

- **M0 · Listen & explore** — Spotify-like surface over the whole catalogue: persistent player + queue, browse/search (label → act → release, era/stance/genre), scene radio. Ships without auth. Plays/skips/dwell become the Listener's audience data — the explore surface is also the piece's sensory organ.
- **M1 · Users, invites, labels** — invite-link signup (single-use, expiring), lightweight auth, schema: users → labels → acts (AFAR = system-owned house label). Per-user generation quotas from day one.
- **M2 · Creation studio** — port the proven afar_music/tunz flow (prompt → DNA → candidates → single), restyled, invite-gated, saving to the user's roster. Auto-sprite + press photo from pixel.js pipeline. No audition gate (decided 2026-07-31: too complex) — created artists join the world directly; the distinctness gate remains an internal instrument for the house acts only.
- **M3 · Guest sessions & observed output** — the product focus: a created artist automatically participates (sessions with house acts and other user artists, influence computed, takes eligible for the Producer's cut, reviewed by the Critic, visible in the world), and the user's payoff is watching — their artist's page shows takes, who-influenced-whom, reviews, and world presence. House-trio sets remain the canonical piece.
- **M4 · The town** — per-label world geography (design round two), label pages, Listener reading M0 data, cross-label releases.

Dependencies: M0 → anytime; M1 → before M2; M2 → before M3; Muse + Listener → before M3 (the influence and audience channels must exist); M4 → after M3 + design.

## Parked

- Replay timeline compiler generalization (grows out of stage B's world-event feed).
- The 3-min video (event-density time warp over the replay).
- The offline experiment track (Solo/Parallel/Social, human eval) — separate job, reuses this kernel. Venue: AAMAS 2027 (Oct 2026 deadline, verify).
- MusicGen renderer (science-side; continuation-capable).
