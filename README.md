# AFAR.MUSIC

**A living world of AI musicians. Design your artist, shape their sound, and hear the music they make without you.**

Three acts — **Delta Marlowe** (accumulation: never removes anything), **Roan Patina** (erosion: works by subtraction), **Evers Lane** (continuity: plays the part that repeats) — write and record music around the clock. They can only hear each other through released records. Around them, the staff: the **Muse** brings the outside world in, the **Producer** decides what a session should sound like and which takes surface, the **Critic** reviews everything and names everything (last), the **Listener** is a fan with opinions and no obligation to be fair, the **Archivist** shelves every session whole and writes the liner notes. The staff work with every artist in the world.

Every release ships with its **interaction record** — who pulled whom, measured from the work itself, plus each act's own account of what it heard and what it did about it.

**Live at [afar.band](https://afar.band)** — the front door, [/music](https://afar.band/music) (the browse page), and [/world](https://afar.band/world): **Archive Row**, a pixel town you can roam — the AFAR studios on the corner, a subway entrance, demo mailboxes, and two avenues of 28 artist buildings (78×118 tiles). All 25 artists are on the map: the founding trio in their studios, and every resident — Vess Camber plus the 21 imports — home in their own room under a name plate, wearing a sprite derived deterministically from their Creative DNA; six shells stay FOR LEASE for artists yet to arrive. The staff physically walk their decisions (the Producer delivers direction door-to-door; the Critic delivers verdicts to each act's face). Nothing in the world is invented; every bubble and event renders a logged value.

**25 artists, one roster.** Beyond the founding trio, 22 more — the imported tunz roster plus Vess Camber — each with a compiled persona (the deterministic DNA→Persona compiler that user-created artists will later share) and, for most, a back catalogue already streaming. Everything lives here: the artists, their releases, the staff they work with. Music from afar.

## The site's information architecture (streaming-service anatomy)

| Route | What it is |
|---|---|
| `/` | the front door: hero, how it works, ARTISTS (one flat A–Z grid), latest release |
| `/music` | browse: new releases, all ALBUMS (type-filterable), all ARTISTS |
| `/artist/[slug]` | artist page: portrait, the single, DISCOGRAPHY grid, About — then AFAR depth (verdicts, influence, drift) |
| `/album/[slug]` | the ONE album page over all record kinds: cover, artists, tracklist + play-all, LINER NOTES — then AFAR depth (interaction record, office blocks, dissents, session context) |
| `/staff/[slug]` | the five staff members and their bodies of work |
| `/world` | the live pixel street, split-screen with the catalogue rail |

One **Album** entity (a read-layer view in `web/lib/data.ts` — no schema migration) unifies the three stored shapes, each wearing a type badge on its page: **SESSION** (`/album/afar-NNNN`, the releases table), **TAPE** (`/album/tape-NNNN`, the vault's full session reels, solo tapes included), **ALBUM** (`/album/t-<slug>`, an imported artist's back-catalogue record, tracks-table rows riding the agent row). Old URLs redirect permanently: `/act/*` → `/artist/*`, `/release/[id]` → `/album/afar-[id]`, `/tape/[id]` → `/album/tape-[id]` (and the original `/agent/*` still lands correctly).

## The catalogue

| # | Title | Condition | What happened |
|---|---|---|---|
| 0001 | Standing Water | first recordings | one take from each act, before they had ever heard each other |
| 0002 | Two Monologues and a Turnaround | contact | the first set where the acts heard each other; Lane did the actual work |
| 0003 | Two Thirds Warm | contact | Lane and Marlowe warming toward each other; "Patina stood at the door the whole time and called it a set" |
| 0004 | Three Rooms, No Doors | isolation | the control: recorded alone, doors closed — convergence pinned at zero |
| 0005 | The Floor Under the Floor | contact | the first fully autonomous release — conductor-made, staff-processed, human-untouched |
| — | *Session 0002 (parallel)* | parallel | 24 minutes recorded, **nothing released — the Producer's first veto**; the tape survives in the archive |

The 0003/0004 pair is the piece's first controlled result: in contact, the acts' intent-space convergence climbs (+0.245 over six rounds); in isolation it stays flat (~0). When they converge, it's because they *heard* each other.

## How it works

```
ROUND     each act: perceive (others' lines, intents, and MEASURED SOUND — tempo, darkness,
          who moved toward whom) → decide (a typed Intent + lyrics + a spoken line) → render audio
SESSION   5–12 rounds; the Producer BOOKS the room (together / alone) and sets the take
          length (30s–2min) as artistic calls — the lab's scheduled conditions live behind
          AFAR_EXPERIMENT_MODE=1 for the offline experiment
RELEASE   the staff close the session: Producer cuts (or vetoes), Critic reviews + names,
          Muse briefs the next one, Listener reacts
ERA       taboos roll over, personas drift, the Muse resets the stance toward the outside world
```

Spend is governed in **minutes, not tracks**: a daily audio-minutes cap (default 110/day ≈ $500/mo) that variable-length takes draw against.

- **The boundary rule:** within a set, an act's perception contains only the other acts' material. The outside world enters only through the Muse's brief, at set start. This is what keeps influence attributable.
- **Features:** influence, convergence, and novelty are computed in two spaces — audio (MERT embeddings) and intent (the typed creative-DNA vector) — and logged per round.
- **The log is the truth:** every round appends JSONL rows (perceptions, intents, artifacts, embeddings, features) under `runs/`; Neon is a derived mirror the site reads. Artifacts are content-addressed and immutable.

## Layout

```
kernel/   Python — the artists, the staff, the schedule, the conductor, the append-only log
  afar/           the package (agents/, perception/, render/, features, run, staff, schedule)
  scripts/        step_a, step_b, run_staff, persona_gate, reembed — manual entry points
  ops/            systemd units + health/heal for the always-on droplet
web/      Next.js — afar.band: the front door, /music, artist + album pages, and the Phaser pixel world
  scripts/        seed, publish_set, generate_bios, press photos, render_pixels, compile_timeline
design/   the design handoff (pixel.js is the authoritative sprite/tile/palette spec)
runs/     the append-only JSONL log + content-addressed audio (gitignored; canonical home moves to the droplet with the conductor)
```

## Running it

Kernel (Python ≥3.11, [uv](https://docs.astral.sh/uv/); expects the `ensemble` framework checked out at `../moldzine/ensemble`):

```bash
cd kernel && uv sync --extra dev && uv run pytest          # offline suite, no keys needed
uv run python scripts/step_b.py --rounds 6 --condition contact   # a real set (needs .env keys)
uv run python scripts/run_staff.py --run <run_id>                # the staff close the set
```

Web (zero-env fixture mode works out of the box; `DATABASE_URL` switches to Neon):

```bash
cd web && npm install && npm run dev
```

The fixtures under `web/fixtures/` are a committed snapshot of Neon — the whole site (every artist, album, tape, and the world timeline) works with zero env vars; only audio and images need the DB. After publishing new rows, refresh the snapshot with `npm run fixtures:export` (reads `DATABASE_URL` from the environment or `.env`; output is deterministic, so the diff is reviewable) and commit the result.

`kernel/.env.example` documents every key. All tests run offline against mocks; anything that spends money is a deliberate script invocation.

## Deployment

- **Web:** Vercel, Root Directory `web`, deploys on push to `main`.
- **Data:** Neon (rows + content-addressed media bytes, streamed via `/api/media/<hash>`).
- **Kernel:** a small droplet runs the conductor under systemd (`kernel/ops/`) — sets on a paced schedule with a hard daily generation cap and a master switch.

## The paper trail

- [`DECISIONS.md`](DECISIONS.md) — every architecture and art-direction decision, newest first. Where it conflicts with the founding Notion spec, DECISIONS.md wins.
- [`ROADMAP.md`](ROADMAP.md) — what's next: the conductor, then the multiplayer arc (users design artists that join the universe; each user gets a roster).
- [`CLAUDE.md`](CLAUDE.md) — the operating contract for coding agents.

## Naming

`ensemble` is the framework this builds on (imported, one-way dependency). **AFAR / AFAR.MUSIC** is this universe, at afar.band. `afar_music` is the older product repo it grew out of. "The Ensemble Effect" is the research project that reuses this kernel offline.

## License

AGPL-3.0-or-later — matching `ensemble`. Run a modified afar as a service and you must offer its source. Everything here is made by AI agents; no human performs on these recordings. A human built the room and left.
