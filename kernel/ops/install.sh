#!/usr/bin/env bash
# Provision/upgrade the AFAR droplet to run the conductor unattended.
# Idempotent: safe to re-run for upgrades. Ported from mold/ops/install.sh,
# adapted to this droplet's layout (everything under /root/projects, run as
# root — the box does exactly one thing).
set -euo pipefail

AFAR_ROOT=${AFAR_ROOT:-/root/projects/AFAR}
ENSEMBLE_ROOT=${ENSEMBLE_ROOT:-/root/projects/moldzine/ensemble}
UV=${UV:-/root/.local/bin/uv}

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }

echo "==> repos (pull current branches, ff-only)"
git -C "$AFAR_ROOT" pull --ff-only
git -C "$ENSEMBLE_ROOT" pull --ff-only

echo "==> python deps (dev + listen + publish extras)"
(cd "$AFAR_ROOT/kernel" && "$UV" sync --extra dev --extra listen --extra publish)

echo "==> dirs"
mkdir -p /etc/afar /var/lib/afar "$AFAR_ROOT/runs"

echo "==> env file"
if [ ! -f /etc/afar/afar.env ]; then
  install -m 0600 "$AFAR_ROOT/kernel/ops/afar.env.example" /etc/afar/afar.env
  echo "    NOTE: fill /etc/afar/afar.env (keys, DATABASE_URL) before enabling AFAR_ENABLED=1"
fi

echo "==> systemd units"
install -m 0644 "$AFAR_ROOT"/kernel/ops/afar.service \
                "$AFAR_ROOT"/kernel/ops/afar-health.service \
                "$AFAR_ROOT"/kernel/ops/afar-heal@.service \
                "$AFAR_ROOT"/kernel/ops/afar-health.timer \
                /etc/systemd/system/
chmod 0755 "$AFAR_ROOT"/kernel/ops/heal.sh "$AFAR_ROOT"/kernel/ops/health.sh
systemctl daemon-reload
systemctl enable --now afar.service afar-health.timer

echo "==> status"
systemctl --no-pager --lines=0 status afar.service afar-health.timer || true
echo "==> done. The conductor idles until AFAR_ENABLED=1 in /etc/afar/afar.env"
echo "    (then: systemctl restart afar)"
