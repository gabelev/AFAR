#!/usr/bin/env bash
# Healing handler. Invoked by afar-heal@<failed-unit>.service.
# Ported from mold/ops/heal.sh — same strategy, simpler ground: the JSONL log
# is append-only and the conductor resumes idempotently from its cursor, so a
# dead conductor needs no tree surgery. Healing is:
#   1. notify (if AFAR_NOTIFY_URL set)
#   2. re-kick the failed unit ONCE (marker file prevents heal-loops)
set -uo pipefail

FAILED_UNIT=${1:-unknown}
STATE_DIR=${AFAR_STATE_DIR:-/var/lib/afar}
MARKER="$STATE_DIR/heal-$FAILED_UNIT.marker"

log() { echo "[heal:$FAILED_UNIT] $*"; }

notify() {
  local msg="$1"
  log "$msg"
  if [ -n "${AFAR_NOTIFY_URL:-}" ]; then
    curl -fsS -m 10 -d "afar: $msg" "$AFAR_NOTIFY_URL" >/dev/null 2>&1 || log "notify failed (webhook unreachable)"
  fi
}

mkdir -p "$STATE_DIR"

# Marker-file loop guard: one re-kick per 6h window; a second failure inside
# the window means a human is needed — notify and stop.
if [ -f "$MARKER" ] && [ $(( $(date +%s) - $(stat -c %Y "$MARKER") )) -lt 21600 ]; then
  notify "unit $FAILED_UNIT failed AGAIN after a heal re-kick — human needed. journalctl -u $FAILED_UNIT"
  exit 0   # do not loop; the notification is the output
fi

case "$FAILED_UNIT" in
  afar.service)
    touch "$MARKER"
    notify "afar.service entered failed state (Restart= exhausted); re-kicking once"
    systemctl reset-failed afar.service 2>/dev/null || true
    systemctl start afar.service --no-block
    ;;
  afar-health.service)
    # Health failures are diagnostics, not crashes: notify, don't re-kick.
    notify "health check failed — see journalctl -u afar-health.service"
    ;;
  *)
    notify "unknown unit failed: $FAILED_UNIT"
    ;;
esac
