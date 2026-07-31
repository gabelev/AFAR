import { describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — plain .mjs build script, no type declarations
import { renderAll } from "./render_pixels.mjs";

const sha = (b: Buffer) => createHash("sha256").update(b).digest("hex");
const pngSize = (b: Buffer) => ({ w: b.readUInt32BE(16), h: b.readUInt32BE(20) });

describe("render_pixels", () => {
  const first = renderAll() as Map<string, Buffer>;
  const second = renderAll() as Map<string, Buffer>;

  it("is deterministic: two renders hash identically", () => {
    expect([...first.keys()]).toEqual([...second.keys()]);
    for (const [name, buf] of first) {
      expect(sha(buf), `hash drift in ${name}`).toBe(sha(second.get(name)!));
    }
  });

  it("emits the spec'd geometry (the 56×34-tile street; 8×12 character frames)", () => {
    expect(pngSize(first.get("bg-era-a.png")!)).toEqual({ w: 896, h: 544 });
    expect(pngSize(first.get("bg-era-b.png")!)).toEqual({ w: 896, h: 544 });
    expect(pngSize(first.get("characters.png")!)).toEqual({ w: 192, h: 128 }); // 12 frames × 8 chars
    expect(pngSize(first.get("tiles.png")!).h).toBe(16);
    expect(pngSize(first.get("props.png")!).h).toBe(32);
  });

  it("matches the committed assets under public/world/", () => {
    const dir = path.resolve(__dirname, "..", "public", "world");
    for (const [name, buf] of first) {
      const committed = readFileSync(path.join(dir, name));
      expect(sha(committed), `${name} is stale — re-run scripts/render_pixels.mjs`).toBe(sha(buf));
    }
  });
});
