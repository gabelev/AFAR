/**
 * Liveness for the world: the pure diff/splice math and the polling loop
 * that let an open tab pick up new releases without a refresh — ever.
 *
 * The contract (DECISIONS.md, world-live-poll):
 * - The world refetches /api/timeline on a slow cadence and DIFFS the
 *   compiled catalogue against what it is playing. Identity of a set-block
 *   is releaseId + runId, in order.
 * - New blocks are SPLICED into the playing sequence, never restarted:
 *   they queue to play right after the current block finishes, then the
 *   sequence carries on, and the loop's wrap-around includes them at their
 *   chronological position thereafter. The clock never resets and the
 *   current block is never interrupted.
 * - Changed display facts on existing blocks (a title the Critic updated)
 *   apply in place — same events, fresher words.
 * - Anything the splice math cannot honour without a restart (a removed,
 *   reordered, or re-published block) is "restructured": the caller adopts
 *   the new catalogue at the next wrap-around instead.
 * - Poll failures are silent: the world keeps playing what it has.
 *
 * Everything except startTimelinePoller is a pure function.
 */

import type { CatalogueEvent, SetBlockMeta, WorldCatalogue } from "@/lib/world/timeline";

/** A set-block's identity: the release plus the run that produced it. */
export function blockKey(b: Pick<SetBlockMeta, "releaseId" | "runId">): string {
  return `${b.releaseId}::${b.runId ?? ""}`;
}

export type CatalogueDiff =
  /** Identical payload — nothing to do. */
  | { kind: "noop" }
  /**
   * The shared prefix changed shape (block removed / reordered /
   * re-published under a new run): a splice cannot honour it without a
   * restart, so the caller should adopt the new catalogue at the next
   * wrap-around instead.
   */
  | { kind: "restructured" }
  /**
   * Same catalogue, possibly extended: `newBlockIndices` are indices into
   * next.blocks for blocks that just landed (appended, chronological);
   * `factsChanged` means some existing block's display facts (title, era,
   * lines…) changed and apply in place.
   */
  | { kind: "updated"; newBlockIndices: number[]; factsChanged: boolean };

/**
 * Compare the playing catalogue with a freshly fetched one, by ordered
 * block identity (releaseId+runId). Append-only growth and in-place fact
 * changes are "updated"; anything else that would force a restart is
 * "restructured".
 */
export function diffCatalogue(prev: WorldCatalogue, next: WorldCatalogue): CatalogueDiff {
  const prevKeys = prev.blocks.map(blockKey);
  const nextKeys = next.blocks.map(blockKey);
  if (nextKeys.length < prevKeys.length) return { kind: "restructured" };
  for (let i = 0; i < prevKeys.length; i++) {
    if (nextKeys[i] !== prevKeys[i]) return { kind: "restructured" };
  }

  // The shared event region must keep its shape — same kinds, same block
  // ownership, same count — or the playing cursor stops meaning anything.
  const shared = prev.events.length;
  if (next.events.length < shared) return { kind: "restructured" };
  for (let i = 0; i < shared; i++) {
    if (next.events[i].kind !== prev.events[i].kind || next.events[i].block !== prev.events[i].block) {
      return { kind: "restructured" };
    }
  }
  // Every event beyond the shared region must belong to a NEW block.
  for (let i = shared; i < next.events.length; i++) {
    if (next.events[i].block < prevKeys.length) return { kind: "restructured" };
  }

  const newBlockIndices: number[] = [];
  for (let i = prevKeys.length; i < nextKeys.length; i++) newBlockIndices.push(i);
  // A block always stages at least its transition beat; a grown block list
  // with no new events means the payload is not what the splice expects.
  if (newBlockIndices.length > 0 && next.events.length === shared) return { kind: "restructured" };

  const factsChanged =
    JSON.stringify(prev.blocks) !== JSON.stringify(next.blocks.slice(0, prev.blocks.length)) ||
    JSON.stringify(prev.events) !== JSON.stringify(next.events.slice(0, shared));

  if (newBlockIndices.length === 0 && !factsChanged) return { kind: "noop" };
  return { kind: "updated", newBlockIndices, factsChanged };
}

/**
 * The splice: the order of event indices to play AFTER the current event
 * finishes, given that events[firstNewEventIndex..] just landed. New
 * blocks play as next-up — right after the current block's remaining
 * events — then the rest of the old order runs, then the order wraps to
 * the top of the catalogue (index 0) and the natural chronological loop,
 * which now includes the new blocks at their proper position, continues.
 * The clock never resets; the current event is never cut short.
 */
export function splicePlayOrder(
  events: readonly Pick<CatalogueEvent, "block">[],
  currentEventIndex: number,
  firstNewEventIndex: number,
): number[] {
  const order: number[] = [];
  const currentBlock = events[currentEventIndex]?.block;
  let j = currentEventIndex + 1;
  // 1) let the current block finish
  while (j < firstNewEventIndex && events[j].block === currentBlock) order.push(j++);
  // 2) the arrivals play next
  for (let k = firstNewEventIndex; k < events.length; k++) order.push(k);
  // 3) then the rest of the old order
  for (; j < firstNewEventIndex; j++) order.push(j);
  // 4) and the loop wraps to the top; natural order carries on from there
  order.push(0);
  return order;
}

/** "A NEW RECORD JUST LANDED — AFAR-0005 · <TITLE>" (lamp-tone caption). */
export function arrivalCaption(arrivals: readonly SetBlockMeta[]): string {
  const first = arrivals[0];
  const base = `A NEW RECORD JUST LANDED — ${first.catalogueNo} · ${first.title.toUpperCase()}`;
  return arrivals.length > 1 ? `${base} (+${arrivals.length - 1} MORE)` : base;
}

/** The rail's NOW line for an arrival, in its lowercase register. */
export function arrivalNowLine(arrivals: readonly SetBlockMeta[]): string {
  const first = arrivals[0];
  const base = `just landed: ${first.catalogueNo} · ${first.title}`;
  return arrivals.length > 1 ? `${base} (+${arrivals.length - 1} more)` : base;
}

/** Poll cadence: ~75s with ±15s jitter so open tabs don't fetch in step. */
export const POLL_BASE_MS = 75_000;
export const POLL_JITTER_MS = 15_000;

export function pollDelayMs(random: () => number = Math.random): number {
  return POLL_BASE_MS + Math.round((random() * 2 - 1) * POLL_JITTER_MS);
}

/** The document surface the poller watches; injectable for tests. */
export interface PollerDoc {
  readonly hidden: boolean;
  addEventListener(type: "visibilitychange", cb: () => void): void;
  removeEventListener(type: "visibilitychange", cb: () => void): void;
}

export interface TimelinePollerOptions {
  /** Fetch the compiled catalogue; return null (or throw) on failure. */
  fetchCatalogue(): Promise<WorldCatalogue | null>;
  /** Called with every successfully fetched catalogue (diffing is the caller's). */
  onCatalogue(cat: WorldCatalogue): void;
  doc: PollerDoc;
  /** Delay to the next poll; defaults to pollDelayMs(). */
  delayMs?(): number;
}

/**
 * Refetch the timeline on a jittered cadence while the tab is visible.
 * Hidden tab: polling pauses. Back to visible: one immediate fetch, then
 * the normal cadence. Failures are silent — the world keeps playing the
 * catalogue it has. Returns a stop function.
 */
export function startTimelinePoller(opts: TimelinePollerOptions): () => void {
  const delayMs = opts.delayMs ?? (() => pollDelayMs());
  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight = false;
  let stopped = false;

  const schedule = () => {
    if (stopped || opts.doc.hidden) return;
    timer = setTimeout(() => void poll(), delayMs());
  };

  const poll = async () => {
    timer = null;
    if (stopped || opts.doc.hidden || inFlight) return;
    inFlight = true;
    try {
      const cat = await opts.fetchCatalogue();
      if (cat && !stopped) opts.onCatalogue(cat);
    } catch {
      /* silent: keep playing the current catalogue */
    } finally {
      inFlight = false;
    }
    schedule();
  };

  const onVisibility = () => {
    if (opts.doc.hidden) {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    } else if (timer === null && !inFlight && !stopped) {
      void poll(); // back from hidden: fetch immediately, then resume cadence
    }
  };

  opts.doc.addEventListener("visibilitychange", onVisibility);
  schedule();

  return () => {
    stopped = true;
    if (timer !== null) clearTimeout(timer);
    timer = null;
    opts.doc.removeEventListener("visibilitychange", onVisibility);
  };
}
