#!/usr/bin/env bash
# Health check for the AFAR droplet. Invoked by afar-health.timer (every 30m).
# Checks the failures Restart= can't see. Exit nonzero -> afar-heal@ fires.
# Ported from mold/ops/healthcheck.sh; the staleness watchdog is keyed to the
# newest JSONL event mtime under runs/ — the conductor heartbeats hourly even
# when idle, and a DISABLED conductor is a HEALTHY conductor (it says so, on
# schedule, in runs/conductor/conductor.jsonl).
set -uo pipefail

AFAR_ROOT=${AFAR_ROOT:-/root/projects/AFAR}
RUNS_ROOT=${AFAR_RUNS_ROOT:-$AFAR_ROOT/runs}
SETS_PER_DAY=${AFAR_SETS_PER_DAY:-3}
ENABLED=${AFAR_ENABLED:-0}
FAILED=0

note() { echo "[health] $*"; }
fail() { echo "[health] FAIL: $*"; FAILED=1; }

# 1. Repos present and readable.
for repo in "$AFAR_ROOT" "$AFAR_ROOT/../moldzine/ensemble"; do
  [ -d "$repo/.git" ] || fail "missing repo: $repo"
done

# 2. Disk space (fail under 1 GiB free — audio accumulates).
avail_kb=$(df --output=avail "$AFAR_ROOT" | tail -1 | tr -d ' ')
if [ "${avail_kb:-0}" -lt 1048576 ]; then
  fail "low disk: ${avail_kb}KB free on $AFAR_ROOT"
fi

# 3. The conductor unit is running (Restart=always should keep it so).
if ! systemctl is-active --quiet afar.service; then
  fail "afar.service is not active"
fi

# 4. Staleness watchdog: the "all green but nothing happening" failure.
#    Newest mtime across every JSONL row file under runs/. Threshold:
#    - disabled: heartbeats land hourly -> 3h of silence means a wedged loop;
#    - enabled: one set interval (24h / AFAR_SETS_PER_DAY), floor 3h — the
#      pacing sleep also heartbeats hourly, so this is generous.
newest=$(find "$RUNS_ROOT" -name '*.jsonl' -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1)
if [ -z "${newest:-}" ]; then
  fail "no JSONL events found under $RUNS_ROOT"
else
  now=$(date +%s)
  age_hours=$(( (now - newest) / 3600 ))
  if [ "$ENABLED" = "1" ]; then
    threshold=$(awk -v spd="$SETS_PER_DAY" 'BEGIN { t = 24 / spd; if (t < 3) t = 3; printf "%d", t + 0.999 }')
  else
    threshold=3
  fi
  if [ "$age_hours" -gt "$threshold" ]; then
    fail "log stale: newest JSONL event ${age_hours}h ago (threshold ${threshold}h, enabled=$ENABLED)"
  else
    note "log fresh: newest JSONL event ${age_hours}h ago (threshold ${threshold}h, enabled=$ENABLED)"
  fi
fi

# 5. Recent unit failures.
if systemctl is-failed --quiet afar.service 2>/dev/null; then
  fail "unit in failed state: afar.service"
fi

if [ "$FAILED" -eq 0 ]; then
  note "all checks passed"
fi
exit "$FAILED"
