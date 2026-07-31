import type { Release } from "@/lib/data";

/**
 * Presentation metadata for the three acts, from the design handoff
 * (design/handoff/README.md + the .dc.html frames). Keyed by the stable
 * mineral ids — entity ids never change; everything here is display-only.
 *
 * accent      — the act's colour (chips, graph nodes, sprites). Never remaps.
 * inkOnPaper  — the darkened variant the design uses for the act's mono
 *               text on the paper ground (CONTINUITY keeps oxide as-is).
 * node / mini — the act's position on the etched-plate cover (480 viewBox)
 *               and on the home page's mini plate (120 viewBox).
 * verb        — the stance verb the cover uses to label an influence edge
 *               pointing INTO this act (what the act did with what it heard).
 * descriptor  — the stance translated for strangers; the plain line under the
 *               act's name.
 * driftLine   — caption of the silhouette-drift strip on the act page.
 */
export const ACT_DESIGN = {
  keep: {
    initials: "EL",
    accent: "#a34c2e",
    inkOnPaper: "#a34c2e",
    studio: "A",
    press: "/press/press-evers.png",
    verb: "played again",
    descriptor: "Steady, clear — keeps playing what the others walk away from",
    node: { x: 240, y: 108 },
    mini: { x: 60, y: 26 },
    driftLine: "the silhouette is what he is reaching for now — and it is holding.",
  },
  rust: {
    initials: "RP",
    accent: "#71917d",
    inkOnPaper: "#4b6355",
    studio: "B",
    press: "/press/press-roan.png",
    verb: "cut away",
    descriptor: "Sparse, worn — strips a song down to what survives",
    node: { x: 119, y: 318 },
    mini: { x: 31, y: 77 },
    driftLine: "the silhouette is what she is reaching for now — and it is thinning.",
  },
  silt: {
    initials: "DM",
    accent: "#bd9040",
    inkOnPaper: "#7c5e2a",
    studio: "C",
    press: "/press/press-delta.png",
    verb: "layered under",
    descriptor: "Slow, layered — never lets anything go",
    node: { x: 361, y: 318 },
    mini: { x: 89, y: 77 },
    driftLine: "the silhouette is what they are reaching for now — and it is thickening.",
  },
} as const;

export type ActId = keyof typeof ACT_DESIGN;

export function isActId(id: string): id is ActId {
  return id in ACT_DESIGN;
}

/** "0001" -> "AFAR-0001" — the catalogue number, everywhere the design shows one. */
export function catalogueNumber(releaseId: string): string {
  return `AFAR-${releaseId}`;
}

/**
 * The interaction record as the design renders it: one row per influenced
 * act — the strongest MEASURED incoming edge (who pulled them), paired with
 * the act's own words about the take. The notation is measured, the quote is
 * claimed; they are allowed to disagree.
 */
export function interactionRows(
  release: Release,
): { from: string; to: string; quote: string; weight: number }[] {
  return Object.entries(release.rationales)
    .map(([to, quote]) => {
      const incoming = [...release.influence]
        .filter((e) => e.to === to)
        .sort((a, b) => b.weight - a.weight);
      return { from: incoming[0]?.from ?? to, to, quote, weight: incoming[0]?.weight ?? 0 };
    })
    .sort((a, b) => b.weight - a.weight);
}

/** Record-sleeve side labels: first half of the takes are side A, the rest side B. */
export function sideLabel(index: number, total: number): string {
  const aSide = Math.ceil(total / 2);
  return index < aSide ? `A${index + 1}` : `B${index - aSide + 1}`;
}
