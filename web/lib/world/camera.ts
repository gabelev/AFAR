/**
 * Pure camera math for the free camera. The world is a fixed pixel rect;
 * the user may roam it plus a comfortable margin of night void on every
 * side. Kept free of Phaser so the clamp is unit-testable.
 */

export interface Scroll {
  x: number;
  y: number;
}

/** Night-void margin around the building, in world px (6 tiles). */
export const CAMERA_MARGIN = 96;

/**
 * Clamp a camera scroll position (top-left corner, world px) so the view
 * stays within the world rect plus `margin` on every side. When the
 * viewport is larger than the bounded world on an axis, the world is
 * centred on that axis instead.
 */
export function clampScroll(
  x: number,
  y: number,
  viewW: number,
  viewH: number,
  worldW: number,
  worldH: number,
  margin: number = CAMERA_MARGIN,
): Scroll {
  const axis = (v: number, view: number, world: number) => {
    const min = -margin;
    const max = world + margin - view;
    if (max < min) return (world - view) / 2;
    return Math.min(max, Math.max(min, v));
  };
  return { x: axis(x, viewW, worldW), y: axis(y, viewH, worldH) };
}

/**
 * Clamp a camera midpoint (the world-px point at the centre of the view).
 *
 * Phaser's `camera.scrollX/Y` is NOT the view origin once the camera is
 * zoomed — the rendered view is centred on `scroll + canvas/2`, so clamping
 * raw scroll values shifts the reachable range by `canvas·(1 − 1/zoom)/2`,
 * a function of the canvas width (i.e. of the rail state). Free-camera code
 * must clamp the midpoint and hand the result to `centerOn`.
 */
export function clampMidpoint(
  midX: number,
  midY: number,
  viewW: number,
  viewH: number,
  worldW: number,
  worldH: number,
  margin: number = CAMERA_MARGIN,
): Scroll {
  const origin = clampScroll(midX - viewW / 2, midY - viewH / 2, viewW, viewH, worldW, worldH, margin);
  return { x: origin.x + viewW / 2, y: origin.y + viewH / 2 };
}

export interface BoundsRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Camera bounds for Phaser: the world plus the roaming margin, grown (and
 * kept centred on the world) whenever the view outgrows it on an axis, so
 * Phaser's own clamp centres the building instead of pinning it to a
 * corner. Derive these from the CURRENT view size — the canvas resizes when
 * the rail toggles or the window resizes.
 */
export function cameraBounds(
  viewW: number,
  viewH: number,
  worldW: number,
  worldH: number,
  margin: number = CAMERA_MARGIN,
): BoundsRect {
  const w = Math.max(worldW + 2 * margin, viewW);
  const h = Math.max(worldH + 2 * margin, viewH);
  return { x: (worldW - w) / 2, y: (worldH - h) / 2, w, h };
}
