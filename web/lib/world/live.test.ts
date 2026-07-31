import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  arrivalCaption,
  arrivalNowLine,
  blockKey,
  diffCatalogue,
  POLL_BASE_MS,
  pollDelayMs,
  splicePlayOrder,
  startTimelinePoller,
  type PollerDoc,
} from "@/lib/world/live";
import {
  compileCatalogue,
  type TimelineSource,
  type WorldCatalogue,
} from "@/lib/world/timeline";

const NAMES = { silt: "Delta Marlowe", rust: "Roan Patina", keep: "Evers Lane" };

/** Release-row-shaped block, one round: [transition, round] once compiled. */
function block(releaseId: string, over: Partial<TimelineSource> = {}): TimelineSource {
  return {
    releaseId,
    runId: `run-${releaseId}`,
    title: `Record ${releaseId}`,
    era: "2020s",
    set: Number(releaseId),
    condition: "isolation",
    rounds: 1,
    names: NAMES,
    linesByRound: [{ silt: "layering", rust: "stripping", keep: "holding" }],
    artifactsByRound: [{ silt: "hash-s", rust: "hash-r", keep: "hash-k" }],
    intentEdgesByRound: {},
    ...over,
  };
}

/** A two-round contact block: compiles to [transition, round, listening, round]. */
function contactBlock(releaseId: string, over: Partial<TimelineSource> = {}): TimelineSource {
  return block(releaseId, {
    condition: "contact",
    rounds: 2,
    linesByRound: [
      { silt: "laying the floor", rust: "finding what is true", keep: "leaving it plain" },
      { silt: "still layering", rust: "still stripping", keep: "still holding" },
    ],
    artifactsByRound: [
      { silt: "hash-s0", rust: "hash-r0", keep: "hash-k0" },
      { silt: "hash-s1", rust: "hash-r1", keep: "hash-k1" },
    ],
    intentEdgesByRound: {
      "1": {
        "silt<-rust": -0.8, "silt<-keep": -0.6,
        "rust<-silt": -0.9, "rust<-keep": -1.3,
        "keep<-silt": -0.4, "keep<-rust": -1.2,
      },
    },
    ...over,
  });
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

describe("blockKey", () => {
  it("is releaseId + runId", () => {
    expect(blockKey({ releaseId: "0005", runId: "run-a" })).toBe("0005::run-a");
    expect(blockKey({ releaseId: "0005" })).toBe("0005::");
  });
});

describe("diffCatalogue", () => {
  const playing = compileCatalogue({ blocks: [contactBlock("0002"), block("0004")] });

  it("no-op on an identical payload", () => {
    expect(diffCatalogue(playing, clone(playing))).toEqual({ kind: "noop" });
  });

  it("detects appended blocks (a new release landed)", () => {
    const next = compileCatalogue({
      blocks: [contactBlock("0002"), block("0004"), block("0005", { title: "Fifth Wind" })],
    });
    const diff = diffCatalogue(playing, next);
    expect(diff).toEqual({ kind: "updated", newBlockIndices: [2], factsChanged: false });
  });

  it("detects several appended blocks at once", () => {
    const next = compileCatalogue({
      blocks: [contactBlock("0002"), block("0004"), block("0005"), block("0006")],
    });
    expect(diffCatalogue(playing, next)).toEqual({
      kind: "updated",
      newBlockIndices: [2, 3],
      factsChanged: false,
    });
  });

  it("detects changed display facts on an existing block (title update in place)", () => {
    const next = compileCatalogue({
      blocks: [contactBlock("0002", { title: "Retitled by the Critic" }), block("0004")],
    });
    const diff = diffCatalogue(playing, next);
    expect(diff).toEqual({ kind: "updated", newBlockIndices: [], factsChanged: true });
    // the fresher facts ride the next catalogue itself — nothing to merge
    expect(next.blocks[0].title).toBe("Retitled by the Critic");
    expect(next.blocks[0].catalogueNo).toBe("AFAR-0002");
  });

  it("append + fact change together reports both", () => {
    const next = compileCatalogue({
      blocks: [contactBlock("0002", { title: "Retitled" }), block("0004"), block("0005")],
    });
    expect(diffCatalogue(playing, next)).toEqual({
      kind: "updated",
      newBlockIndices: [2],
      factsChanged: true,
    });
  });

  it("restructured: a block re-published under a different run", () => {
    const next = compileCatalogue({
      blocks: [contactBlock("0002", { runId: "run-republished" }), block("0004")],
    });
    expect(diffCatalogue(playing, next)).toEqual({ kind: "restructured" });
  });

  it("restructured: a block removed or reordered", () => {
    expect(
      diffCatalogue(playing, compileCatalogue({ blocks: [block("0004")] })),
    ).toEqual({ kind: "restructured" });
    expect(
      diffCatalogue(playing, compileCatalogue({ blocks: [block("0004"), contactBlock("0002")] })),
    ).toEqual({ kind: "restructured" });
  });

  it("restructured: a shared block's event shape changed", () => {
    // same identity, but the block now stages a different event sequence
    const next = compileCatalogue({
      blocks: [contactBlock("0002", { condition: "isolation" }), block("0004")],
    });
    expect(diffCatalogue(playing, next)).toEqual({ kind: "restructured" });
  });
});

describe("splicePlayOrder", () => {
  // playing = [T0 R0 L0 R0 | T1 R1], arrivals land at index 6: [T2 R2]
  const playing = compileCatalogue({ blocks: [contactBlock("0002"), block("0004")] });
  const next = compileCatalogue({ blocks: [contactBlock("0002"), block("0004"), block("0005")] });
  const firstNew = playing.events.length; // 6

  it("mid-block: the current block finishes, arrivals play next, then the rest, then the wrap", () => {
    // currently on the first round of block 0 (index 1)
    expect(splicePlayOrder(next.events, 1, firstNew)).toEqual([
      2, 3, // the current block finishes (listening + final round)
      6, 7, // the arrivals play next-up
      4, 5, // then the rest of the old order (block 1)
      0, // then the loop wraps to the top — the natural order now includes the arrival
    ]);
  });

  it("current block is the last old block: arrivals follow it directly", () => {
    // currently on block 1's transition (index 4)
    expect(splicePlayOrder(next.events, 4, firstNew)).toEqual([5, 6, 7, 0]);
  });

  it("current event is the last of its block: arrivals are immediately next-up", () => {
    // currently on block 0's final round (index 3)
    expect(splicePlayOrder(next.events, 3, firstNew)).toEqual([6, 7, 4, 5, 0]);
  });

  it("never cuts the current event and never resets the clock (order only)", () => {
    const order = splicePlayOrder(next.events, 1, firstNew);
    expect(order).not.toContain(1); // the playing event is not rescheduled
    expect(new Set(order).size).toBe(order.length); // nothing plays twice this cycle
  });
});

describe("arrival staging text", () => {
  const meta = (id: string, title: string) => ({
    releaseId: id,
    catalogueNo: `AFAR-${id}`,
    title,
    era: "2020s",
    set: 5,
    condition: "contact",
    conditionLine: "RECORDED TOGETHER — EACH ACT COULD HEAR THE OTHERS",
    names: NAMES,
  });

  it("announces the record in plain language, lamp register", () => {
    expect(arrivalCaption([meta("0005", "Fifth Wind")])).toBe(
      "A NEW RECORD JUST LANDED — AFAR-0005 · FIFTH WIND",
    );
    expect(arrivalNowLine([meta("0005", "Fifth Wind")])).toBe(
      "just landed: AFAR-0005 · Fifth Wind",
    );
  });

  it("counts extra simultaneous arrivals", () => {
    const two = [meta("0005", "Fifth Wind"), meta("0006", "Sixth")];
    expect(arrivalCaption(two)).toBe("A NEW RECORD JUST LANDED — AFAR-0005 · FIFTH WIND (+1 MORE)");
    expect(arrivalNowLine(two)).toBe("just landed: AFAR-0005 · Fifth Wind (+1 more)");
  });
});

describe("pollDelayMs", () => {
  it("jitters ±15s around the 75s base", () => {
    expect(pollDelayMs(() => 0.5)).toBe(POLL_BASE_MS);
    expect(pollDelayMs(() => 0)).toBe(60_000);
    expect(pollDelayMs(() => 1)).toBe(90_000);
  });
});

describe("startTimelinePoller", () => {
  const catalogue = compileCatalogue({ blocks: [block("0002")] });

  function fakeDoc(hidden = false) {
    const listeners = new Set<() => void>();
    const doc = {
      hidden,
      addEventListener: (_: "visibilitychange", cb: () => void) => void listeners.add(cb),
      removeEventListener: (_: "visibilitychange", cb: () => void) => void listeners.delete(cb),
      setHidden(h: boolean) {
        doc.hidden = h;
        for (const cb of [...listeners]) cb();
      },
    };
    return doc as PollerDoc & { setHidden(h: boolean): void };
  }

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("fetches on the cadence and hands the catalogue to the caller", async () => {
    const fetchCatalogue = vi.fn<() => Promise<WorldCatalogue | null>>().mockResolvedValue(catalogue);
    const onCatalogue = vi.fn();
    const stop = startTimelinePoller({ fetchCatalogue, onCatalogue, doc: fakeDoc(), delayMs: () => 1000 });

    expect(fetchCatalogue).not.toHaveBeenCalled(); // the initial fetch is the world's own
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchCatalogue).toHaveBeenCalledTimes(1);
    expect(onCatalogue).toHaveBeenCalledWith(catalogue);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchCatalogue).toHaveBeenCalledTimes(2);
    stop();
  });

  it("failures are silent and the cadence continues", async () => {
    const fetchCatalogue = vi
      .fn<() => Promise<WorldCatalogue | null>>()
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce(null) // non-ok response
      .mockResolvedValue(catalogue);
    const onCatalogue = vi.fn();
    const stop = startTimelinePoller({ fetchCatalogue, onCatalogue, doc: fakeDoc(), delayMs: () => 1000 });

    await vi.advanceTimersByTimeAsync(2000);
    expect(fetchCatalogue).toHaveBeenCalledTimes(2);
    expect(onCatalogue).not.toHaveBeenCalled(); // kept playing the current catalogue
    await vi.advanceTimersByTimeAsync(1000);
    expect(onCatalogue).toHaveBeenCalledTimes(1);
    stop();
  });

  it("pauses while the tab is hidden, resumes with an immediate fetch", async () => {
    const fetchCatalogue = vi.fn<() => Promise<WorldCatalogue | null>>().mockResolvedValue(catalogue);
    const doc = fakeDoc();
    const stop = startTimelinePoller({ fetchCatalogue, onCatalogue: vi.fn(), doc, delayMs: () => 1000 });

    doc.setHidden(true);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchCatalogue).not.toHaveBeenCalled(); // hidden: no polling at all

    doc.setHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchCatalogue).toHaveBeenCalledTimes(1); // visible again: immediate fetch
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchCatalogue).toHaveBeenCalledTimes(2); // then the normal cadence
    stop();
  });

  it("stop() ends the loop for good", async () => {
    const fetchCatalogue = vi.fn<() => Promise<WorldCatalogue | null>>().mockResolvedValue(catalogue);
    const doc = fakeDoc();
    const stop = startTimelinePoller({ fetchCatalogue, onCatalogue: vi.fn(), doc, delayMs: () => 1000 });
    stop();
    await vi.advanceTimersByTimeAsync(5000);
    doc.setHidden(true);
    doc.setHidden(false); // a late visibility flip must not revive it
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchCatalogue).not.toHaveBeenCalled();
  });
});
