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
