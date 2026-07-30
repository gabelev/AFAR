import type { InfluenceEdge, PlayerId } from "@/lib/data";

/**
 * The interaction record as a fixed triangle: SILT / RUST / KEEP, with one
 * directed edge per ordered pair. Stroke width encodes influence weight —
 * how much of one player's material shaped another's take. Placeholder
 * renderer: positions are fixed; only the weights come from data.
 */

const NODES: Record<PlayerId, { x: number; y: number; label: string }> = {
  silt: { x: 210, y: 70, label: "SILT" },
  rust: { x: 80, y: 292, label: "RUST" },
  keep: { x: 340, y: 292, label: "KEEP" },
};

const NODE_R = 36;
const BEND = 30;

function edge(from: PlayerId, to: PlayerId) {
  const a = NODES[from];
  const b = NODES[to];
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  // Each direction bows to its own side, so the pair reads as two arrows.
  const nx = -dy / len;
  const ny = dx / len;
  const cx = (a.x + b.x) / 2 + nx * BEND;
  const cy = (a.y + b.y) / 2 + ny * BEND;

  const trim = (px: number, py: number, tx: number, ty: number, r: number) => {
    const d = Math.hypot(tx - px, ty - py);
    return [px + ((tx - px) / d) * r, py + ((ty - py) / d) * r];
  };
  const [sx, sy] = trim(a.x, a.y, cx, cy, NODE_R + 2);
  const [ex, ey] = trim(b.x, b.y, cx, cy, NODE_R + 8);

  // Quadratic midpoint (t = 0.5), nudged outward for the weight label.
  const mx = 0.25 * sx + 0.5 * cx + 0.25 * ex + nx * 11;
  const my = 0.25 * sy + 0.5 * cy + 0.25 * ey + ny * 11;

  return { path: `M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`, mx, my };
}

export function InfluenceGraph({ influence }: { influence: InfluenceEdge[] }) {
  return (
    <svg
      viewBox="0 0 420 370"
      role="img"
      aria-label="Influence graph: directed edges between SILT, RUST, and KEEP weighted by influence"
      style={{ width: "100%", maxWidth: 440, height: "auto" }}
    >
      <defs>
        <marker
          id="influence-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-accent)" />
        </marker>
      </defs>

      {influence.map((e) => {
        const { path, mx, my } = edge(e.from, e.to);
        return (
          <g key={`${e.from}-${e.to}`}>
            <path
              d={path}
              fill="none"
              stroke="var(--color-accent)"
              strokeOpacity={0.35 + e.weight * 0.6}
              strokeWidth={0.75 + e.weight * 4.5}
              markerEnd="url(#influence-arrow)"
            />
            <text
              x={mx}
              y={my}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={10}
              fill="var(--color-neutral-600)"
            >
              {e.weight.toFixed(2)}
            </text>
          </g>
        );
      })}

      {(Object.keys(NODES) as PlayerId[]).map((id) => {
        const n = NODES[id];
        return (
          <g key={id}>
            <circle
              cx={n.x}
              cy={n.y}
              r={NODE_R}
              fill="var(--color-surface)"
              stroke="var(--color-divider)"
              strokeWidth={1}
            />
            <text
              x={n.x}
              y={n.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={14}
              letterSpacing={1.5}
              fill="var(--color-text)"
              style={{ fontFamily: "var(--font-heading)", fontWeight: 600 }}
            >
              {n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
