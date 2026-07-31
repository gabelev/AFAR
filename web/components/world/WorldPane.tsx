"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { consumeLastFlown, onFly } from "@/lib/world/bus";
import { routeTarget } from "@/lib/world/resolve";
import type { WorldHandle } from "@/components/world/createWorld";

/**
 * The persistent world pane (left of the split). Lives in the root layout,
 * so the Phaser world survives right-pane navigation; route changes centre
 * the camera on the relevant actor or room instead of remounting anything.
 * Phaser is dynamically imported — the catalogue never pays for it on the
 * server or in the first bundle.
 */
export function WorldPane() {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<WorldHandle | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const pathnameRef = useRef(pathname);
  useEffect(() => {
    pathnameRef.current = pathname;
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;
    let handle: WorldHandle | null = null;
    const container = containerRef.current;
    if (!container) return;

    void import("@/components/world/createWorld").then(async ({ createWorld }) => {
      if (cancelled) return;
      handle = await createWorld(container, {
        onNavigate: (route) => router.push(route),
        era: new URLSearchParams(window.location.search).get("era") === "B" ? "B" : "A",
      });
      if (cancelled) {
        handle.destroy();
        return;
      }
      handleRef.current = handle;
      // centre on whatever route we loaded into (deep link / hard refresh)
      handle.setAnchor(routeTarget(pathnameRef.current), true);
    });

    const offFly = onFly((target) => handleRef.current?.flyTo(target));
    return () => {
      cancelled = true;
      offFly();
      handleRef.current = null;
      handle?.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Route change → the camera glides to the page's subject (unless a
  // WorldLink already flew it there as part of fly-then-navigate).
  useEffect(() => {
    const handle = handleRef.current;
    if (!handle) return;
    const target = routeTarget(pathname);
    const flown = consumeLastFlown();
    const sameSpot =
      flown && target && Math.abs(flown.tx - target.tx) < 0.01 && Math.abs(flown.ty - target.ty) < 0.01;
    handle.setAnchor(target, !sameSpot);
  }, [pathname]);

  return (
    <div
      ref={containerRef}
      className="world-container"
      role="img"
      aria-label="The AFAR world, drawn in pixels. The three acts record in separate studios; the archive below is the only room where one act can hear another."
    />
  );
}
