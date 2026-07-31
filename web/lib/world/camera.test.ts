import { describe, expect, it } from "vitest";
import { CAMERA_MARGIN, clampScroll } from "@/lib/world/camera";

// The world's real dimensions (createWorld.ts): 33×34 tiles at 16px.
const W = 528;
const H = 544;

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
});
