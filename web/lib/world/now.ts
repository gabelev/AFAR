"use client";

/**
 * The NOW line: a one-line feed of current world activity, published by
 * the Phaser world and consumed by the rail's NOW row. Same shape as the
 * fly bus — module-level pub/sub, no context, survives route changes.
 */

type NowListener = (line: string | null) => void;

let current: string | null = null;
const listeners = new Set<NowListener>();

export function setNow(line: string | null): void {
  current = line;
  for (const l of listeners) l(line);
}

/** Subscribe; the current value replays immediately. Returns unsubscribe. */
export function onNow(listener: NowListener): () => void {
  listeners.add(listener);
  listener(current);
  return () => {
    listeners.delete(listener);
  };
}
