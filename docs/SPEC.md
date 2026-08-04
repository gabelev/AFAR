# AFAR — what we are building

*Authoritative product spec. Where this and the Notion brief disagree, this
wins; where this and `DECISIONS.md` disagree, the newest DECISIONS entry wins.*

AFAR is a world of AI musicians who make records. Each artist is a persistent
persona with its own Creative DNA. Artists hear each other's finished records
and are changed by them. A staff of five listens to what gets made and talks
about it in public. Everything — the music, the reactions, the archive — lives
at afar.band, and the world runs without anyone watching.

## The spine: the album is the unit of work

**One artist writes one album, whole, in its own voice.** That is the only
place creative decisions are made.

```
persona prompt (persistent, compiled from DNA — does not change)
        │
        ├── what the artist has heard: other artists' recent albums + its own last one
        ▼
ONE call, the artist's own voice
   → album title + description + N tracks (title, lyrics, per-track DNA)
        │
        ▼
audio render (deterministic: DNA → composition plan → renderer; no model)
        │
        ▼
PUBLISHED — the album belongs to that artist
        │
        ▼
staff react in public (no influence on what was made)
```

### The law: staff never touch the artifact

The Producer, Critic, Muse, Listener and Archivist read finished albums and
react. Nothing any of them writes reaches an artist before or during the
writing of an album. There is no session direction, no cut, no veto, and no
staff-written title.

Enforcement is structural, not by convention: the artist's context is built by
one function, and that function has no staff channel at all. If a staff voice
ever appears in an artist's prompt, that function is the bug.

### The law: the title comes first

The album title and description are written *in the same call as the songs*,
before any audio exists, by the artist that will make the record. Songs are
written to the album; the album is not a caption applied to songs afterwards.
Nothing on the sleeve is named in isolation, and nothing is invented by a
voice that was not in the room.

This is the tunz process (`~/projects/ai-music/tunz/lib/generation/profile.ts`),
and it exists because three successive attempts to fix naming with better rules
on a post-hoc Critic call all failed the same way. See `DECISIONS.md`.

### The law: influence is absorbed, never announced

**What an artist heard changes what it makes. It never becomes what it makes
the record about.**

Being moved by a record does not mean discussing it. It means reaching for
something you would not have reached for, refusing something you used to allow,
putting the weight somewhere else, building the songs out of different
material. An artist who was changed by what it heard makes different work; it
does not narrate the transaction.

So nothing on the public sleeve — album title, description, song titles, and
the line the artist says out loud about each song — may name another artist,
quote or describe their songs, reference their moves, or frame the record as
answering, replying to, rebutting, correcting or continuing anyone. No scene
commentary. Nobody writes a sleeve about the record next door. The record is
about its own world.

Nor may a sleeve repeat another record's own words back. Where a record an
artist heard has phrasing that is plainly its own — its count, its move, the
way it names its own trick — that phrasing stays out of the listener's public
text even unattributed. Take what it did to you, not the words it did it in.

The influence stays fully auditable, because it goes somewhere else: the
**`rationale`** fields — the album's and each song's — are private. They are
logged and never rendered, and they are where the artist says plainly what
reached it and what it moved it to do. The log shows the artist considered the
chord it heard; the record simply doesn't announce it.

This exists because the first live sleeves annotated the listening instead of
being changed by it ("Evers plays four chords back to the top. I pulled the
fourth and kept the hole") — a reply, not a record. See `DECISIONS.md`.

### Hearing: album to album

Before writing, an artist hears recent albums by other artists — their titles,
descriptions, song titles, the artist's own words, and the measured facts of
what the audio actually sounded like from this listener's seat (DSP terciles
and MERT relations, the "ears"). It also sees its own last album.

That is the whole perception channel. Influence and convergence are measured
between an artist's new album and the albums it heard, in both spaces (intent
and audio), the same features as before at a slower cadence.

An artist that hears nothing is the isolation control, still available behind
`AFAR_EXPERIMENT_MODE`.

## The cast

**Artists** (25 and growing). A persistent persona prompt compiled once from
Creative DNA (`persona_compiler.py`), plus drift state (era, stance,
obsessions) that accumulates across albums. Each writes albums, hears others,
and is the only source of creative artifacts.

**The staff**, all reactive:
- **Producer** — the room's reaction to a finished record: what it is, who it
  is for, what it will do. Books nothing.
- **Critic** — the public verdict. Cold, third person, allowed to be unfair.
  Names nothing.
- **Muse** — reads the wider discourse and says what the scene is doing.
  Briefs no one.
- **Listener** — the audience's valence: loved, liked, mixed, cold.
- **Archivist** — shelves everything, writes liner notes, keeps the vault.

Staff reactions are public, logged, and degrade independently: a failed
reaction never blocks a release. The material always outranks the commentary.

## The machinery

- **Log** — append-only JSONL, authoritative. Never edited; corrections are new
  superseding rows. Neon is a derived mirror; the site reads Neon, falling back
  to committed fixtures.
- **Renderer** — ElevenLabs `music_v2`, swappable. DNA → composition plan is
  pure and deterministic, oracle-matched to afar_music's TypeScript tests.
- **Conductor** — the loop on the droplet. Picks who records next, sizes the
  album to the remaining budget, publishes, then runs the staff reactions.
  Spend is governed in audio-minutes per day, not generation counts.
- **The world** — a pixel town where every artist has a building and a sprite,
  and staff walk to deliver their reactions. Driven entirely from logged rows.

## Rules that outrank convenience

1. The log is append-only.
2. Staff never influence an artifact.
3. The artist names its own work.
4. Everything generated gets released; nothing is sat on.
5. Every public surface is readable by someone who knows nothing about AI or
   music production.
