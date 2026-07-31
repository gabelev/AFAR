import { describe, expect, it } from "vitest";
import { CAMERA_MARGIN, cameraBounds, clampMidpoint, clampScroll } from "@/lib/world/camera";

// The world's real dimensions (createWorld.ts): 33×34 tiles at 16px.
const W = 528;
const H = 544;

// Rail-open split on a 1440×900 window: the world pane is 55% wide and the
// player bar owns 72px, so the canvas is 792×828 — at 2× zoom the view is
// 396×414 world px. These are the dimensions the pan bug shipped with.
const RAIL_VIEW_W = 792 / 2;
const RAIL_VIEW_H = 828 / 2;

describe("free-camera clamp", () => {
  it("leaves an in-bounds scroll alone", () => {
    expect(clampScroll(100, 120, 300, 300, W, H, CAMERA_MARGIN)).toEqual({ x: 100, y: 120 });
  });

  it("clamps to the margin of night void, not the building edge", () => {
    const { x, y } = clampScroll(-10_000, -10_000, 300, 300, W, H, CAMERA_MARGIN);
    expect(x).toBe(-CAMERA_MARGIN);
    expect(y).toBe(-CAMERA_MARGIN);
  });

  it("clamps the far edge so the view never leaves world + margin", () => {
    const { x, y } = clampScroll(10_000, 10_000, 300, 200, W, H, CAMERA_MARGIN);
    expect(x).toBe(W + CAMERA_MARGIN - 300);
    expect(y).toBe(H + CAMERA_MARGIN - 200);
  });

  it("centres an axis when the viewport outgrows world + margins", () => {
    const viewW = W + 2 * CAMERA_MARGIN + 100; // wider than everything
    const { x, y } = clampScroll(0, 100, viewW, 200, W, H, CAMERA_MARGIN);
    expect(x).toBe((W - viewW) / 2);
    expect(y).toBe(100); // the other axis still clamps normally
  });

  it("is idempotent — clamping a clamped scroll changes nothing", () => {
    const once = clampScroll(9999, -9999, 400, 400, W, H, CAMERA_MARGIN);
    expect(clampScroll(once.x, once.y, 400, 400, W, H, CAMERA_MARGIN)).toEqual(once);
  });

  it("rail open (canvas 792×828 at 2×): the full margin-to-margin range is pannable", () => {
    const left = clampScroll(-10_000, 0, RAIL_VIEW_W, RAIL_VIEW_H, W, H, CAMERA_MARGIN);
    expect(left.x).toBe(-CAMERA_MARGIN); // left void edge reachable
    const right = clampScroll(10_000, 0, RAIL_VIEW_W, RAIL_VIEW_H, W, H, CAMERA_MARGIN);
    expect(right.x).toBe(W + CAMERA_MARGIN - RAIL_VIEW_W);
    expect(right.x + RAIL_VIEW_W).toBe(W + CAMERA_MARGIN); // right void edge on screen
  });
});

describe("midpoint clamp (what the free camera actually feeds Phaser's centerOn)", () => {
  it("clamps so the view edges land on world + margin, rail-open dimensions", () => {
    const right = clampMidpoint(10_000, 0, RAIL_VIEW_W, RAIL_VIEW_H, W, H, CAMERA_MARGIN);
    expect(right.x + RAIL_VIEW_W / 2).toBe(W + CAMERA_MARGIN); // right visible edge
    const left = clampMidpoint(-10_000, 0, RAIL_VIEW_W, RAIL_VIEW_H, W, H, CAMERA_MARGIN);
    expect(left.x - RAIL_VIEW_W / 2).toBe(-CAMERA_MARGIN); // left visible edge
  });

  it("leaves an in-bounds midpoint alone", () => {
    const mid = clampMidpoint(W / 2, H / 2, RAIL_VIEW_W, RAIL_VIEW_H, W, H, CAMERA_MARGIN);
    expect(mid).toEqual({ x: W / 2, y: H / 2 });
  });

  it("centres the world when the view outgrows world + margins", () => {
    const view = W + 2 * CAMERA_MARGIN + 100;
    const mid = clampMidpoint(10_000, H / 2, view, RAIL_VIEW_H, W, H, CAMERA_MARGIN);
    expect(mid.x).toBe(W / 2);
  });
});

describe("camera bounds from the current view size", () => {
  it("is world + margin on both axes for a normal split-pane view", () => {
    expect(cameraBounds(RAIL_VIEW_W, RAIL_VIEW_H, W, H, CAMERA_MARGIN)).toEqual({
      x: -CAMERA_MARGIN,
      y: -CAMERA_MARGIN,
      w: W + 2 * CAMERA_MARGIN,
      h: H + 2 * CAMERA_MARGIN,
    });
  });

  it("grows to the view, centred on the world, when the view is wider (rail closed, wide window)", () => {
    const view = 960; // 1920px canvas at 2×
    const b = cameraBounds(view, RAIL_VIEW_H, W, H, CAMERA_MARGIN);
    expect(b.w).toBe(view);
    expect(b.x).toBe((W - view) / 2); // building centred, not pinned to a corner
    expect(b.h).toBe(H + 2 * CAMERA_MARGIN); // the other axis is unaffected
  });
});
