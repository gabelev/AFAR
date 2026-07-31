/**
 * NOW / REPLAY: the world's two ways of being watched, as pure state.
 *
 * NOW (the default): the acts are simply in the studio — ambient idle,
 * small non-claiming movements, their last logged lines dimmed on the
 * walls. The latest record sits "on the shelf" at the turntable; clicking
 * it (or the rail control) plays that block's staging ONCE, then the world
 * settles back to idle. When the live poll splices in a new release, the
 * arrival staging runs, the new block plays once, and idle resumes with
 * the new record as latest.
 *
 * REPLAY: the existing chronological catalogue loop, exactly as before,
 * plus a release picker that jumps the loop to a chosen block's start.
 *
 * The scene owns timers and sprites; this module owns the decisions —
 * which phase we are in, which event index plays next in a once-through,
 * and how a picker choice resolves to an event index. All pure, all
 * tested. The catalogue's block order is chronological (oldest first,
 * newest last — compile_timeline.mjs and kernel/afar/publish.py both
 * write it that way), so "the latest record" is simply the last block.
 */

import type { CatalogueEvent, WorldActId, WorldCatalogue } from "@/lib/world/timeline";

export type WorldMode = "now" | "replay";

/** Why a once-through is playing: the shelf click vs. a live arrival. */
export type OnceReason = "record" | "arrival";

export type ModePhase =
  /** REPLAY: the catalogue loop runs; the scene's own cursor drives it. */
  | { kind: "replay" }
  /** NOW, idle: ambience only — nothing scripted is playing. */
  | { kind: "idle" }
  /** NOW, playing a block once; `queue` is the event indices still to play. */
  | { kind: "once"; queue: readonly number[]; reason: OnceReason };

/** The world loads in NOW mode, idle. Nothing persists across reloads. */
export function initialPhase(): ModePhase {
  return { kind: "idle" };
}

export function modeOf(phase: ModePhase): WorldMode {
  return phase.kind === "replay" ? "replay" : "now";
}

/**
 * The rail toggle: NOW ↔ REPLAY. Leaving NOW abandons any once-through in
 * progress (the queue is dropped); leaving REPLAY lands on idle.
 */
export function toggledPhase(phase: ModePhase): ModePhase {
  return phase.kind === "replay" ? { kind: "idle" } : { kind: "replay" };
}

/**
 * Begin a once-through of `order` (event indices). Returns the phase plus
 * the first index to run; an empty order is a no-op back to idle.
 */
export function beginOnce(
  order: readonly number[],
  reason: OnceReason,
): { phase: ModePhase; first: number | null } {
  if (order.length === 0) return { phase: { kind: "idle" }, first: null };
  return { phase: { kind: "once", queue: order.slice(1), reason }, first: order[0] };
}

/**
 * An event finished during a once-through: the next index to play, or
 * null — the once-through is over and the world settles back to idle.
 */
export function advanceOnce(phase: ModePhase): { phase: ModePhase; next: number | null } {
  if (phase.kind !== "once" || phase.queue.length === 0) {
    return { phase: { kind: "idle" }, next: null };
  }
  return {
    phase: { kind: "once", queue: phase.queue.slice(1), reason: phase.reason },
    next: phase.queue[0],
  };
}

/** The newest block: last in the chronologically ordered block list. */
export function latestBlockIndex(cat: Pick<WorldCatalogue, "blocks">): number {
  return cat.blocks.length - 1;
}

/**
 * The once-through order for ONE block: its round/listening events in
 * natural order, WITHOUT the transition beat — "NEXT: …" announces an
 * upcoming record, and a shelf replay is not upcoming; the idle caption
 * already names it.
 */
export function blockPlayOrder(
  events: readonly Pick<CatalogueEvent, "kind" | "block">[],
  block: number,
): number[] {
  const order: number[] = [];
  events.forEach((ev, i) => {
    if (ev.block === block && ev.kind !== "transition") order.push(i);
  });
  return order;
}

/**
 * The once-through order for a live arrival: every non-transition event
 * from the first new index on (a splice appends whole new blocks, so this
 * is exactly the arrivals' staging). The "A NEW RECORD JUST LANDED"
 * caption does the announcing; the transition beats stay out.
 */
export function arrivalPlayOrder(
  events: readonly Pick<CatalogueEvent, "kind" | "block">[],
  firstNewEventIndex: number,
): number[] {
  const order: number[] = [];
  for (let i = firstNewEventIndex; i < events.length; i++) {
    if (events[i].kind !== "transition") order.push(i);
  }
  return order;
}

/**
 * Picker → block start: the index of the block's first event (its
 * transition beat — the loop announces the record, then plays it, exactly
 * as the natural loop would). -1 if the block stages nothing.
 */
export function blockStartIndex(
  events: readonly Pick<CatalogueEvent, "block">[],
  block: number,
): number {
  return events.findIndex((ev) => ev.block === block);
}

/** One row of the rail's release picker. */
export interface PickerEntry {
  block: number;
  catalogueNo: string;
  title: string;
}

/** The rail's release picker: catalogue number + title per block, in order. */
export function pickerEntries(cat: Pick<WorldCatalogue, "blocks">): PickerEntry[] {
  return cat.blocks.map((b, block) => ({ block, catalogueNo: b.catalogueNo, title: b.title }));
}

/** Idle caption: `LAST RECORD: <TITLE> · THE ACTS ARE IN THE STUDIO`. */
export function idleCaption(cat: WorldCatalogue): string {
  const latest = cat.blocks[latestBlockIndex(cat)];
  return `LAST RECORD: ${latest.title.toUpperCase()} · THE ACTS ARE IN THE STUDIO`;
}

/** The shelf line at the turntable: `LAST RECORD: <TITLE> — <catalogueNo> · play`. */
export function shelfLine(cat: WorldCatalogue): string {
  const latest = cat.blocks[latestBlockIndex(cat)];
  return `LAST RECORD: ${latest.title.toUpperCase()} — ${latest.catalogueNo} · click to play`;
}

/** The rail's NOW line while idle, in its lowercase register. */
export function idleNowLine(cat: WorldCatalogue): string {
  const latest = cat.blocks[latestBlockIndex(cat)];
  return `in the studio · last record: ${latest.catalogueNo} · ${latest.title}`;
}

/**
 * The acts' last-known logged lines: the final round of the latest block
 * that stages one. Idle shows these dimmed — remembered words, never
 * invented ones. Null if the catalogue stages no rounds at all.
 */
export function lastLoggedLines(
  cat: Pick<WorldCatalogue, "events">,
): Record<WorldActId, string> | null {
  for (let i = cat.events.length - 1; i >= 0; i--) {
    const ev = cat.events[i];
    if (ev.kind === "round") return ev.lines;
  }
  return null;
}
