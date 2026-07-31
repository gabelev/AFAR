import { describe, expect, it } from "vitest";
import { createCanvas, type Canvas } from "canvas";
import { createHash } from "node:crypto";

// The AUTHORITATIVE design spec, imported directly — its painters run fine
// on node-canvas (they only set width/height and use the 2d context).
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — design reference file, no type declarations
import * as design from "../../design/handoff/pixel.js";
// The registry-driven port under test.
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — plain .mjs build script, no type declarations
import { paintWorld, paintStreet, drawResidentRoom, eraPal, T, W, H, SW, SH } from "./lib/pixelspec.mjs";

/**
 * THE ACCEPTANCE GATE for the geometry-registry refactor: rendering the
 * world from web/world-geometry.json + pixelspec's painters must be
 * hash-identical to rendering the design handoff's own pixel.js — the same
 * new spec, drawn twice by independent code paths. If the registry drops,
 * moves, or reorders a single tile, prop, or sprite, these hashes split.
 */

const hashPixels = (cv: Canvas) => {
  const { width, height } = cv;
  const data = cv.getContext("2d").getImageData(0, 0, width, height).data;
  return createHash("sha256").update(Buffer.from(data.buffer, data.byteOffset, data.byteLength)).digest("hex");
};

describe("registry-driven render matches the design spec, pixel for pixel", () => {
  for (const era of ["A", "B"] as const) {
    it(`the house, era ${era} (drawWorld vs registry paintWorld)`, () => {
      const ref = createCanvas(1, 1);
      design.drawWorld(ref, { era, scene: "normal" });
      expect(ref.width).toBe(W * T);
      expect(ref.height).toBe(H * T);

      const ours = createCanvas(W * T, H * T);
      const c = ours.getContext("2d");
      c.imageSmoothingEnabled = false;
      paintWorld(c, eraPal(era), { era, people: true, scene: "normal" });

      expect(hashPixels(ours)).toBe(hashPixels(ref));
    });

    it(`the street, era ${era} (drawStreet vs registry paintStreet)`, () => {
      const ref = createCanvas(1, 1);
      design.drawStreet(ref, { era, scene: "normal" });
      expect(ref.width).toBe(SW * T);
      expect(ref.height).toBe(SH * T);

      const ours = createCanvas(SW * T, SH * T);
      const c = ours.getContext("2d");
      c.imageSmoothingEnabled = false;
      paintStreet(c, eraPal(era), era, "normal");

      expect(hashPixels(ours)).toBe(hashPixels(ref));
    });
  }

  const roomCases: [string, Record<string, unknown>][] = [
    ["vess camber (occupied, amp)", { acc: "#8a6f9e", accD: "#5e4a6c", prop: "amp", occupied: true }],
    ["move-in ready (empty slot)", {}],
    ["a future resident (occupied, reels, custom accent)", { acc: "#bd9040", accD: "#7c5e2a", prop: "reels", occupied: true }],
  ];
  for (const [name, opts] of roomCases) {
    it(`resident room — ${name}`, () => {
      const ref = createCanvas(1, 1);
      design.drawResidentRoom(ref, opts);
      const ours = createCanvas(1, 1);
      drawResidentRoom(ours, opts);
      expect(ours.width).toBe(ref.width);
      expect(ours.height).toBe(ref.height);
      expect(hashPixels(ours)).toBe(hashPixels(ref));
    });
  }
});
