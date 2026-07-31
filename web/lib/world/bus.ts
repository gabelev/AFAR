"use client";

/**
 * Tiny client-side bridge between the right pane and the world. The world
 * pane lives in the root layout (it persists across routes); right-pane
 * links fly the camera through this bus before navigating.
 */

import type { WorldTarget } from "@/lib/world/resolve";

type FlyListener = (target: WorldTarget) => void;

const listeners = new Set<FlyListener>();
let lastFlown: WorldTarget | null = null;

export function onFly(listener: FlyListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Fly the world camera. Returns true if a world is listening. */
export function fly(target: WorldTarget): boolean {
  lastFlown = target;
  for (const l of listeners) l(target);
  return listeners.size > 0;
}

/**
 * Route-change centring calls this to skip a duplicate flight when a
 * WorldLink already flew the camera for the same destination.
 */
export function consumeLastFlown(): WorldTarget | null {
  const t = lastFlown;
  lastFlown = null;
  return t;
}
