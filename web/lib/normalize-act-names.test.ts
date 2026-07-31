import { describe, expect, it } from "vitest";
import { normalizeActNames } from "./normalize-act-names.mjs";

describe("normalizeActNames", () => {
  it("maps capitalized act ids to first names", () => {
    expect(normalizeActNames("Rust, ground cracks so silt has somewhere to go")).toBe(
      "Roan, ground cracks so silt has somewhere to go",
    );
    expect(normalizeActNames("Silt built a floor and called it warm")).toBe(
      "Delta built a floor and called it warm",
    );
  });

  it("handles the vocative Keep", () => {
    expect(normalizeActNames("Keep, that chord doesn't stop ringing")).toBe(
      "Evers, that chord doesn't stop ringing",
    );
  });

  it("handles double vocatives in one line", () => {
    expect(normalizeActNames("Keep, Silt, listen to what's under your resolve.")).toBe(
      "Evers, Delta, listen to what's under your resolve.",
    );
  });

  it("carries possessives over, preserving the apostrophe glyph", () => {
    expect(normalizeActNames("Rust's dead tape and Keep's held chord")).toBe(
      "Roan's dead tape and Evers's held chord",
    );
    expect(normalizeActNames("Silt’s floor-settling")).toBe("Delta’s floor-settling");
  });

  it("never touches lowercase common-noun/verb uses", () => {
    expect(normalizeActNames("it just goes under enough silt to hold weight")).toBe(
      "it just goes under enough silt to hold weight",
    );
    expect(normalizeActNames("everything you keep still rots")).toBe(
      "everything you keep still rots",
    );
    expect(normalizeActNames("keep the hum; rust never sleeps")).toBe(
      "keep the hum; rust never sleeps",
    );
  });

  it("respects word boundaries (no matches inside longer words)", () => {
    expect(normalizeActNames("Keeper of the Rusty Silted gate")).toBe(
      "Keeper of the Rusty Silted gate",
    );
  });

  it("leaves non-strings and empty strings alone", () => {
    expect(normalizeActNames("")).toBe("");
  });

  it("is idempotent", () => {
    const once = normalizeActNames("Rust, I heard the crack — Keep's chord, Silt's loam.");
    expect(normalizeActNames(once)).toBe(once);
  });
});
