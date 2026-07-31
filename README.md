# AFAR

**Creative AI agents building a universe of music.**

Three players — **SILT** (accumulation), **RUST** (erosion), **KEEP** (continuity) — make music at each other, continuously. They can hear each other, until they can't. Around them sits an ecology of non-playing agents: the **Muse** feeds them, the **Producer** shapes and selects, the **Critic** judges and names, the **Listener** loves and hates.

Every release ships with its **interaction record**: the directed influence graph for that set, the convergence curve, and each player's own account of what it heard and what it decided to do about it. The graph is not a diagram *about* the album. It is part of the album.

AFAR is an autonomous multi-agent creative AI system: three acts make music continuously, and every release ships with the record of who influenced whom.

Public face: [afar.band](https://afar.band).

## Layout

```
kernel/   Python — the band, the staff, the conductor, the append-only log
web/      Next.js — the archive and (eventually) the world; deploys to Vercel
runs/     JSONL logs written by the kernel (gitignored)
```

The kernel writes an append-only log; the web layer only reads it. The web app renders from bundled fixtures when `DATABASE_URL` is unset, from Neon when it is set.

## Naming (read this before touching anything)

Four related things have confusingly similar names. The resolution:

| Name | What it is | Where |
|---|---|---|
| `ensemble` | the domain-agnostic creative-agent **framework** | imported by this repo |
| **`AFAR`** (this repo) | the **installation** — the live art piece | [afar.band](https://afar.band) |
| `afar_music` | the AI-artist-builder **product** (separate repo) | afar.music |
| "The Ensemble Effect" | the offline **research project** that reuses this kernel | not a repo |

## License

AGPL-3.0-or-later — matching the `ensemble` framework this repo builds on. If you run a modified afar as a network service, you must offer its source.
