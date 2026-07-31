import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GraphCover, GraphCoverMini } from "./GraphCover";
import { fixtureReleases, type InfluenceEdge } from "@/lib/data";

/**
 * The cover is a function of the release's influence edges (architecture
 * rule 5) — so the tests are about the function: N directed edges in,
 * N arrowed lines out.
 */

const NAMES = { silt: "Delta Marlowe", rust: "Roan Patina", keep: "Evers Lane" };

const count = (html: string, marker: string) =>
  (html.match(new RegExp(marker, "g")) ?? []).length;

function render(edges: InfluenceEdge[], releaseId = "0001", title = "Standing Water") {
  return renderToStaticMarkup(GraphCover({ releaseId, title, edges, names: NAMES }));
}

describe("GraphCover", () => {
  const release = fixtureReleases[0];

  it("renders one arrowed line per directed influence edge", () => {
    const html = render(release.influence);
    expect(count(html, "data-edge")).toBe(release.influence.length);
    expect(count(html, "data-arrow")).toBe(release.influence.length);
  });

  it("renders all three act nodes in their accent colours", () => {
    const html = render(release.influence);
    expect(count(html, "data-node")).toBe(3);
    for (const accent of ["#a34c2e", "#71917d", "#bd9040"]) {
      expect(html).toContain(accent);
    }
  });

  it("captions the plate with the catalogue number and title", () => {
    const html = render(release.influence);
    expect(html).toContain("AFAR-0001 · STANDING WATER");
  });

  it("marks a self-edge as a dashed recurrence ring, not an arrow", () => {
    const edges: InfluenceEdge[] = [{ from: "keep", to: "keep", weight: 1 }];
    const html = render(edges);
    expect(count(html, "data-edge")).toBe(0);
    expect(html).toContain("EVERS LANE · ×1");
  });

  it("renders an empty record as plate, rings, and nodes alone", () => {
    const html = render([]);
    expect(count(html, "data-edge")).toBe(0);
    expect(count(html, "data-node")).toBe(3);
  });
});

describe("GraphCoverMini", () => {
  it("renders one line per pair of acts with a recorded edge", () => {
    const html = renderToStaticMarkup(GraphCoverMini({ edges: fixtureReleases[0].influence }));
    expect(count(html, "data-pair")).toBe(3); // all three pairs exchange influence
  });

  it("collapses both directions of a pair into a single line", () => {
    const edges: InfluenceEdge[] = [
      { from: "silt", to: "rust", weight: 0.5 },
      { from: "rust", to: "silt", weight: 0.2 },
    ];
    const html = renderToStaticMarkup(GraphCoverMini({ edges }));
    expect(count(html, "data-pair")).toBe(1);
  });
});
