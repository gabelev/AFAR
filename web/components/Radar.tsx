import type { SonicPalette } from "@/lib/intent/schema";

/**
 * A sonic palette as a read-only radar — the agent's signature silhouette.
 * Display only; the web layer never edits intent.
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
  showLabels = false,
}: {
  palette: SonicPalette;
  size?: number;
  showLabels?: boolean;
}) {
  const center = size / 2;
  const radius = size / 2 - (showLabels ? 34 : 8);

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
      role="img"
      aria-label="The shape of this act's sound — a chart with one dial for each pair of opposites, such as loud versus quiet"
    >
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon
          key={ring}
          points={AXES.map((_, i) => point(i, ring).join(",")).join(" ")}
          fill="none"
          stroke="var(--color-divider)"
          strokeWidth={1}
        />
      ))}
      {AXES.map((_, i) => {
        const [x, y] = point(i, 1);
        return (
          <line
            key={i}
            x1={center}
            y1={center}
            x2={x}
            y2={y}
            stroke="var(--color-divider)"
            strokeWidth={1}
          />
        );
      })}
      <polygon
        points={points}
        fill="color-mix(in srgb, var(--color-accent) 18%, transparent)"
        stroke="var(--color-accent)"
        strokeWidth={1.5}
      />
      {showLabels &&
        AXES.map((axis, i) => {
          const [x, y] = point(i, 1.28);
          return (
            <text
              key={axis.key}
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={9}
              letterSpacing={0.8}
              fill="var(--color-neutral-600)"
              style={{ textTransform: "uppercase" }}
            >
              {axis.label}
            </text>
          );
        })}
    </svg>
  );
}
