import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { PressPhoto } from "./PressPhoto";
import { Radar } from "./Radar";
import type { SonicPalette } from "@/lib/intent/schema";

/**
 * Every act must have a face (architecture rule: DNA → palette → Radar).
 * These tests pin the fallback ladder: imageUrl → static press copy →
 * Radar silhouette plate — and never an empty gap when a palette exists.
 */

const PALETTE: SonicPalette = {
  pristineLofi: 0.55,
  sparseDense: -0.2,
  coldWarm: 0.4,
  improvisedStructured: 0.3,
  loudQuiet: 0.65,
  organicSynthetic: -0.15,
  darkHopeful: 0.2,
};

const render = (props: Parameters<typeof PressPhoto>[0]) =>
  renderToStaticMarkup(createElement(PressPhoto, props));

describe("Radar", () => {
  it("renders the palette silhouette as an svg in the act accent", () => {
    const html = renderToStaticMarkup(Radar({ palette: PALETTE }));
    expect(html).toContain("<svg");
    expect(html).toContain("--act-accent");
  });
});

describe("PressPhoto fallback ladder", () => {
  it("renders the imageUrl when present (Radar plate wired as the onError fallback)", () => {
    const html = render({ imageUrl: "/api/media/abc", palette: PALETTE, alt: "X press photo" });
    expect(html).toContain('src="/api/media/abc"');
  });

  it("falls back to the Radar plate when an act has no imageUrl at all", () => {
    const html = render({ imageUrl: null, palette: PALETTE, alt: "X press photo" });
    expect(html).toContain("<svg");
    expect(html).toContain('aria-label="X press photo"');
  });

  it("prefers the checked-in press copy over the Radar when both exist", () => {
    const html = render({
      pressSrc: "/press/press-evers.png",
      imageUrl: null,
      palette: PALETTE,
      alt: "X press photo",
    });
    expect(html).toContain('src="/press/press-evers.png"');
    expect(html).not.toContain("<svg");
  });

  it("still renders a quiet plate (no gap) when there is neither image nor palette", () => {
    const html = render({ imageUrl: null, palette: null, alt: "X press photo" });
    expect(html).toContain('aria-label="X press photo"');
  });
});
