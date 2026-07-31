import type { CSSProperties } from "react";
import type { SonicPalette } from "@/lib/intent/schema";

/**
 * A sonic palette as a read-only radar — the act's signature silhouette.
 * Every act has a palette, so this can ALWAYS render: it is the guaranteed
 * fallback face when an act has no portrait in media (or the bytes 404 in
 * fixture mode). Display only; the web layer never edits intent.
 *
 * Colors ride the per-act scope (`data-act` sets --act-accent), so the
 * silhouette carries the act's accent wherever it appears.
 */

const AXES: { key: keyof SonicPalette; label: string }[] = [
  { key: "pristineLofi", label: "Lo-fi" },
  { key: "sparseDense", label: "Dense" },
  { key: "coldWarm", label: "Warm" },
  { key: "improvisedStructured", label: "Structured" },
  { key: "loudQuiet", label: "Quiet" },
  { key: "organicSynthetic", label: "Synthetic" },
  { key: "darkHopeful", label: "Hopeful" },
];

export function Radar({
  palette,
  size = 180,
  style,
}: {
  palette: SonicPalette;
  size?: number;
  style?: CSSProperties;
}) {
  const center = size / 2;
  const radius = size / 2 - 8;

  const point = (i: number, magnitude: number) => {
    const angle = (Math.PI * 2 * i) / AXES.length - Math.PI / 2;
    return [center + Math.cos(angle) * radius * magnitude, center + Math.sin(angle) * radius * magnitude];
  };

  // Signed −1..1 maps to 0..1 distance from center: −1 pole hugs the center,
  // +1 pole reaches the rim, neutral sits midway. The shape is the signature.
  const points = AXES.map((axis, i) => point(i, (palette[axis.key] + 1) / 2))
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      style={style}
      role="img"
      aria-label="The shape of this act's sound — a chart with one dial for each pair of opposites, such as loud versus quiet"
    >
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon
          key={ring}
          points={AXES.map((_, i) => point(i, ring).join(",")).join(" ")}
          fill="none"
          stroke="var(--hairline)"
          strokeWidth={1}
        />
      ))}
      {AXES.map((_, i) => {
        const [x, y] = point(i, 1);
        return (
          <line key={i} x1={center} y1={center} x2={x} y2={y} stroke="var(--hairline)" strokeWidth={1} />
        );
      })}
      <polygon
        points={points}
        fill="color-mix(in srgb, var(--act-accent, var(--oxide)) 18%, transparent)"
        stroke="var(--act-accent, var(--oxide))"
        strokeWidth={1.5}
      />
    </svg>
  );
}
