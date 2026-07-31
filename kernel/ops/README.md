# AFAR ops — the droplet that runs the piece forever

The conductor (`afar.conductor`) runs as a systemd service on one droplet.
That droplet is **the only kernel writer**: the append-only JSONL log under
`runs/` lives there canonically (rule 3 — the log is authoritative; Neon is a
derived mirror; any local copy is a read-only backup).

## Layout (this droplet)

| what | where |
| --- | --- |
| AFAR checkout | `/root/projects/AFAR` (branch tracked by `install.sh`) |
| ensemble checkout | `/root/projects/moldzine/ensemble` (editable path dep) |
| the canonical log | `/root/projects/AFAR/runs/` |
| conductor state | `runs/conductor/` (cursor rows + `gen_budget.json`) |
| environment | `/etc/afar/afar.env` (0600; from `afar.env.example`) |
| heal markers | `/var/lib/afar/` |

## Units

- **afar.service** — `uv run python -m afar.conductor`, `Restart=always`.
  With `AFAR_ENABLED=0` (the shipped default) it idles and writes a
  `disabled` heartbeat row hourly — that is the healthy parked state.
  SIGTERM finishes the current round, checkpoints, exits 0.
- **afar-health.timer / .service** — every 30 min: repos present, disk,
  unit active, and the staleness watchdog over the newest JSONL event mtime
  (threshold derived from `AFAR_SETS_PER_DAY` when enabled; 3h against the
  hourly heartbeats when disabled).
- **afar-heal@.service + heal.sh** — failure handler with a 6h marker-file
  loop guard: one re-kick, then a human (via `AFAR_NOTIFY_URL` if set).

## Install / upgrade

```sh
ssh root@<droplet>
/root/projects/AFAR/kernel/ops/install.sh   # idempotent: pull, uv sync, units
```

## Flipping the switch

```sh
vi /etc/afar/afar.env        # AFAR_ENABLED=1 (check cadence + cap first)
systemctl restart afar
journalctl -fu afar
```

Spend at the defaults: ~3 sets/day (jittered ±20%), 5–12 rounds/set ×3 acts
≈ 24–54 generations/day, hard-capped at `AFAR_DAILY_GEN_CAP=60`; at the cap
the conductor sleeps to the next UTC day. The generation counter persists in
`runs/conductor/gen_budget.json` — restarts do not reset spend.

## Supervised smoke (no money, no Neon writes)

```sh
cd /root/projects/AFAR/kernel
ANTHROPIC_API_KEY= AFAR_ENABLED=1 AFAR_RENDERER=mock AFAR_EMBEDDER=mock \
  /root/.local/bin/uv run python -m afar.conductor --smoke
```

(`ANTHROPIC_API_KEY=` empty forces the mock model too — a smoke spends
nothing anywhere.)

One 2-round set through the full chain (direct → set → staff → publish
**dry-run**), rows tagged `smoke`, cursor untouched — and the whole run is
written to a sibling `runs-smoke/` root, so nothing mock ever seeds the
canonical log (the real Muse reads briefs/reactions across ALL of runs/).
