import { mkdtempSync, mkdirSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { findRun, newestReleaseRecordFile, selectedTakes } from "./publish_set.mjs";

/**
 * The kernel's append-only correction path (kernel/scripts/reembed.py) leaves
 * SEVERAL release-*.json files in a run dir; publishing must pick the newest
 * by mtime — the corrected record — never the alphabetically-first one.
 */

function runDirWithRecords(records: Array<{ name: string; ageSec: number; body: object }>) {
  const root = mkdtempSync(path.join(tmpdir(), "afar-publish-"));
  const runId = "20990101-000000-step-b-contact";
  const runDir = path.join(root, runId);
  mkdirSync(runDir);
  const now = Date.now() / 1000;
  for (const { name, ageSec, body } of records) {
    const file = path.join(runDir, name);
    writeFileSync(file, JSON.stringify(body));
    utimesSync(file, now - ageSec, now - ageSec);
  }
  return { root, runId, runDir };
}

describe("newestReleaseRecordFile", () => {
  it("picks the newest record by mtime, not by name", () => {
    // The corrected record ("5aba…") sorts BEFORE the superseded one ("121a…")
    // alphabetically — exactly the release 0002 layout — so name order would
    // republish the mock-embedded record.
    const { runDir } = runDirWithRecords([
      { name: "release-121a7fea914e.json", ageSec: 3600, body: { release_id: "old" } },
      { name: "release-5aba762c21c9.json", ageSec: 0, body: { release_id: "new" } },
    ]);
    expect(newestReleaseRecordFile(runDir)).toBe("release-5aba762c21c9.json");
  });

  it("ignores non-record files and returns undefined when none exist", () => {
    const { runDir } = runDirWithRecords([]);
    writeFileSync(path.join(runDir, "artifacts.jsonl"), "");
    writeFileSync(path.join(runDir, "releases.jsonl"), "");
    expect(newestReleaseRecordFile(runDir)).toBeUndefined();
  });
});

describe("findRun", () => {
  it("loads the newest record for an explicit run id", () => {
    const { root, runId } = runDirWithRecords([
      { name: "release-aaaaaaaaaaaa.json", ageSec: 60, body: { release_id: "superseded" } },
      { name: "release-zzzzzzzzzzzz.json", ageSec: 7200, body: { release_id: "oldest" } },
      { name: "release-bbbbbbbbbbbb.json", ageSec: 0, body: { release_id: "corrected" } },
    ]);
    const { record } = findRun(runId, root);
    expect(record.release_id).toBe("corrected");
  });

  it("throws when no run has a release record", () => {
    const root = mkdtempSync(path.join(tmpdir(), "afar-publish-"));
    mkdirSync(path.join(root, "20990101-000000-step-b-contact"));
    expect(() => findRun(undefined, root)).toThrow(/no step-b-contact run/);
  });
});

describe("selectedTakes", () => {
  const artifacts = [
    { silt: "s0", rust: "r0", keep: "k0" },
    { silt: "s1", rust: "r1", keep: "k1" },
    { silt: "s2", rust: "r2", keep: "k2" },
  ];

  it("publishes the Producer's cut when the record carries a staff block, spanning rounds", () => {
    const record = {
      set: { rounds: 3 },
      artifacts,
      staff: {
        producer: {
          selected: {
            silt: { round: 0, take_id: "s0" },
            rust: { round: 2, take_id: "r2" },
            keep: { round: 1, take_id: "k1" },
          },
        },
      },
    };
    expect(selectedTakes(record)).toEqual({
      silt: { round: 0, hash: "s0" },
      rust: { round: 2, hash: "r2" },
      keep: { round: 1, hash: "k1" },
    });
  });

  it("falls back to the final round, mechanically, for pre-staff records", () => {
    const record = { set: { rounds: 3 }, artifacts };
    expect(selectedTakes(record)).toEqual({
      silt: { round: 2, hash: "s2" },
      rust: { round: 2, hash: "r2" },
      keep: { round: 2, hash: "k2" },
    });
  });
});
