import { describe, expect, it } from "vitest";
import {
  advanceOnce,
  arrivalPlayOrder,
  beginOnce,
  blockPlayOrder,
  blockStartIndex,
  idleCaption,
  idleNowLine,
  initialPhase,
  lastLoggedLines,
  latestBlockIndex,
  modeOf,
  pickerEntries,
  shelfLine,
  toggledPhase,
  type ModePhase,
} from "@/lib/world/mode";
import { compileCatalogue, type TimelineSource } from "@/lib/world/timeline";

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

// [0:T b0, 1:R b0, 2:L b0, 3:R b0, 4:T b1, 5:R b1]
const cat = compileCatalogue({ blocks: [contactBlock("0002"), block("0004")] });

describe("the mode state machine", () => {
  it("loads in NOW mode, idle — the new default", () => {
    const phase = initialPhase();
    expect(phase).toEqual({ kind: "idle" });
    expect(modeOf(phase)).toBe("now");
  });

  it("toggles NOW ↔ REPLAY; leaving NOW drops a once-through", () => {
    expect(toggledPhase({ kind: "idle" })).toEqual({ kind: "replay" });
    expect(toggledPhase({ kind: "replay" })).toEqual({ kind: "idle" });
    expect(toggledPhase({ kind: "once", queue: [3, 4], reason: "record" })).toEqual({
      kind: "replay",
    });
  });

  it("modeOf: once-through is still NOW", () => {
    expect(modeOf({ kind: "once", queue: [], reason: "arrival" })).toBe("now");
    expect(modeOf({ kind: "replay" })).toBe("replay");
  });

  it("a once-through plays its queue in order, then settles back to idle", () => {
    const begun = beginOnce([1, 2, 3], "record");
    expect(begun.first).toBe(1);
    let phase: ModePhase = begun.phase;
    const played = [begun.first];
    for (;;) {
      const { phase: p, next } = advanceOnce(phase);
      phase = p;
      if (next === null) break;
      played.push(next);
    }
    expect(played).toEqual([1, 2, 3]);
    expect(phase).toEqual({ kind: "idle" });
  });

  it("an empty order is a no-op back to idle", () => {
    expect(beginOnce([], "arrival")).toEqual({ phase: { kind: "idle" }, first: null });
  });

  it("advancing a non-once phase lands on idle", () => {
    expect(advanceOnce({ kind: "replay" })).toEqual({ phase: { kind: "idle" }, next: null });
    expect(advanceOnce({ kind: "idle" })).toEqual({ phase: { kind: "idle" }, next: null });
  });
});

describe("the shelf: latest block + its once-through order", () => {
  it("the latest record is the last block (the payload is chronological)", () => {
    expect(latestBlockIndex(cat)).toBe(1);
  });

  it("blockPlayOrder: the block's events in order, without the transition beat", () => {
    expect(blockPlayOrder(cat.events, 0)).toEqual([1, 2, 3]);
    expect(blockPlayOrder(cat.events, 1)).toEqual([5]);
    expect(blockPlayOrder(cat.events, 7)).toEqual([]);
  });

  it("arrivalPlayOrder: everything from the splice point on, minus transitions", () => {
    // as if block 1 just landed: its events start at index 4
    expect(arrivalPlayOrder(cat.events, 4)).toEqual([5]);
    expect(arrivalPlayOrder(cat.events, cat.events.length)).toEqual([]);
  });
});

describe("picker → block resolution", () => {
  it("lists catalogue number + title per block, in catalogue order", () => {
    expect(pickerEntries(cat)).toEqual([
      { block: 0, catalogueNo: "AFAR-0002", title: "Record 0002" },
      { block: 1, catalogueNo: "AFAR-0004", title: "Record 0004" },
    ]);
  });

  it("blockStartIndex: the block's transition beat, where the loop jumps to", () => {
    expect(blockStartIndex(cat.events, 0)).toBe(0);
    expect(cat.events[blockStartIndex(cat.events, 1)].kind).toBe("transition");
    expect(blockStartIndex(cat.events, 1)).toBe(4);
    expect(blockStartIndex(cat.events, 9)).toBe(-1);
  });
});

describe("the idle register", () => {
  it("caption: LAST RECORD + the acts are in the studio", () => {
    expect(idleCaption(cat)).toBe("LAST RECORD: RECORD 0004 · THE ACTS ARE IN THE STUDIO");
  });

  it("shelf line names the record and invites the click", () => {
    expect(shelfLine(cat)).toBe("LAST RECORD: RECORD 0004 — AFAR-0004 · click to play");
  });

  it("NOW line keeps the rail's lowercase register", () => {
    expect(idleNowLine(cat)).toBe("in the studio · last record: AFAR-0004 · Record 0004");
  });

  it("last logged lines are the final staged round's — remembered, not invented", () => {
    expect(lastLoggedLines(cat)).toEqual({
      silt: "layering",
      rust: "stripping",
      keep: "holding",
    });
    expect(lastLoggedLines({ events: [] })).toBeNull();
  });
});
