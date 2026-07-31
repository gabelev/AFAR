import { ACT_DESIGN, catalogueNumber, isActId, type ActId } from "@/lib/acts";
import type { InfluenceEdge } from "@/lib/data";

/**
 * The cover IS the influence graph — the etched-plate register from the
 * design handoff (frame 1c): act-colour nodes on concentric hairline rings
 * inside a hatched ring border, directed arrows for the release's measured
 * influence edges, stance-verb labels on the strongest pull into each act,
 * and the catalogue caption. Rendered entirely FROM the release's edges;
 * no stored art (architecture rule 5: the cover is a function, not an agent).
 */

const INK = "#1c1a15";
const PLATE = "#d6cfbc";
const SEC = "#5e5a4f";
const MONO = "IBM Plex Mono, monospace";

type Pt = { x: number; y: number };

/** Perpendicular (left of travel) unit vector for the segment a -> b. */
function leftNormal(a: Pt, b: Pt): Pt {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: dy / len, y: -dx / len };
}

export function GraphCover({
  releaseId,
  title,
  edges,
  names,
  size = 480,
}: {
  releaseId: string;
  title: string;
  edges: InfluenceEdge[];
  names: Record<string, string>;
  size?: number;
}) {
  const directed = edges.filter((e) => e.from !== e.to && isActId(e.from) && isActId(e.to));
  const selfCount = new Map<ActId, number>();
  for (const e of edges) {
    if (e.from === e.to && isActId(e.from)) {
      selfCount.set(e.from, (selfCount.get(e.from) ?? 0) + 1);
    }
  }

  // The strongest measured pull INTO each act gets its stance-verb label.
  const labelled = new Set<InfluenceEdge>();
  for (const id of Object.keys(ACT_DESIGN) as ActId[]) {
    const strongest = [...directed]
      .filter((e) => e.to === id)
      .sort((a, b) => b.weight - a.weight)[0];
    if (strongest) labelled.add(strongest);
  }

  const actIds = Object.keys(ACT_DESIGN) as ActId[];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 480 480"
      role="img"
      aria-label={`Cover of ${catalogueNumber(releaseId)} — the influence graph of ${title}`}
      style={{ background: PLATE, outline: "1px solid var(--hairline-plate)" }}
    >
      <rect x="10" y="10" width="460" height="460" fill="none" stroke={INK} strokeWidth="0.8" />
      <circle cx="240" cy="248" r="182" fill="none" stroke={INK} strokeWidth="8" strokeDasharray="1 5" opacity="0.55" />
      <circle cx="240" cy="248" r="168" fill="none" stroke={INK} strokeWidth="0.7" />
      <circle cx="240" cy="248" r="140" fill="none" stroke={INK} strokeWidth="0.5" />
      <circle cx="240" cy="248" r="112" fill="none" stroke={INK} strokeWidth="0.5" />
      <circle cx="240" cy="248" r="84" fill="none" stroke={INK} strokeWidth="0.5" />
      <circle cx="240" cy="248" r="10" fill="none" stroke={INK} strokeWidth="0.7" />

      {directed.map((e, i) => {
        const from = ACT_DESIGN[e.from as ActId].node;
        const to = ACT_DESIGN[e.to as ActId].node;
        // A reverse edge exists for every ordered pair in real records; nudge
        // each direction to its own left so the two arrows read separately.
        const paired = directed.some((o) => o.from === e.to && o.to === e.from);
        const n = leftNormal(from, to);
        const off = paired ? 4 : 0;
        const x1 = from.x + n.x * off;
        const y1 = from.y + n.y * off;
        const x2 = to.x + n.x * off;
        const y2 = to.y + n.y * off;
        const t = 0.62;
        const ax = x1 + (x2 - x1) * t;
        const ay = y1 + (y2 - y1) * t;
        const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
        const width = (0.6 + e.weight * 1.2).toFixed(2);
        const mx = (x1 + x2) / 2 + n.x * 14;
        const my = (y1 + y2) / 2 + n.y * 14;
        return (
          <g key={`${e.from}-${e.to}-${i}`}>
            <line data-edge x1={x1} y1={y1} x2={x2} y2={y2} stroke={INK} strokeWidth={width} />
            <polygon
              data-arrow
              points="0,-4 9,0 0,4"
              transform={`translate(${ax.toFixed(1)},${ay.toFixed(1)}) rotate(${angle.toFixed(1)})`}
              fill={INK}
            />
            {labelled.has(e) && (
              <text
                x={mx.toFixed(1)}
                y={my.toFixed(1)}
                textAnchor="middle"
                fontFamily={MONO}
                fontSize="9"
                letterSpacing="1"
                fill={SEC}
              >
                {ACT_DESIGN[e.to as ActId].verb}
              </text>
            )}
          </g>
        );
      })}

      {actIds.map((id) => {
        const d = ACT_DESIGN[id];
        const self = selfCount.get(id) ?? 0;
        const top = d.node.y < 248;
        const label = `${(names[id] ?? id).toUpperCase()}${self > 0 ? ` · ×${self}` : ""}`;
        return (
          <g key={id}>
            {self > 0 && (
              <circle
                cx={d.node.x}
                cy={top ? d.node.y - 32 : d.node.y + 32}
                r="20"
                fill="none"
                stroke={d.accent}
                strokeWidth="1"
                strokeDasharray="3 3"
              />
            )}
            <circle data-node cx={d.node.x} cy={d.node.y} r="9" fill={d.accent} />
            <text
              x={d.node.x}
              y={top ? d.node.y - 56 : d.node.y + 30}
              textAnchor="middle"
              fontFamily={MONO}
              fontSize="11"
              letterSpacing="2"
              fill={INK}
            >
              {label}
            </text>
          </g>
        );
      })}

      <text x="240" y="446" textAnchor="middle" fontFamily={MONO} fontSize="12" letterSpacing="4" fill={INK}>
        {catalogueNumber(releaseId)} · {title.toUpperCase()}
      </text>
    </svg>
  );
}

/**
 * The home page's mini plate (frame 1a's latest-release card): two hairline
 * rings, the three nodes, and one plain line per pair of acts with a
 * recorded edge. No text at this size.
 */
export function GraphCoverMini({ edges, size = 120 }: { edges: InfluenceEdge[]; size?: number }) {
  const pairs = new Set<string>();
  for (const e of edges) {
    if (e.from !== e.to && isActId(e.from) && isActId(e.to)) {
      pairs.add([e.from, e.to].sort().join("+"));
    }
  }
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      aria-hidden="true"
      style={{ flex: "none", background: PLATE, outline: "1px solid var(--hairline-frame)" }}
    >
      <circle cx="60" cy="60" r="44" fill="none" stroke={INK} strokeWidth="0.8" />
      <circle cx="60" cy="60" r="30" fill="none" stroke={INK} strokeWidth="0.6" />
      {[...pairs].map((pair) => {
        const [a, b] = pair.split("+") as [ActId, ActId];
        return (
          <line
            data-pair
            key={pair}
            x1={ACT_DESIGN[a].mini.x}
            y1={ACT_DESIGN[a].mini.y}
            x2={ACT_DESIGN[b].mini.x}
            y2={ACT_DESIGN[b].mini.y}
            stroke={INK}
            strokeWidth="0.8"
          />
        );
      })}
      {(Object.keys(ACT_DESIGN) as ActId[]).map((id) => (
        <circle key={id} cx={ACT_DESIGN[id].mini.x} cy={ACT_DESIGN[id].mini.y} r="5" fill={ACT_DESIGN[id].accent} />
      ))}
    </svg>
  );
}
