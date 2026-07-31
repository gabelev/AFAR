"use client";

/**
 * The left pane: the label building as a Phaser 3 world, built from the
 * design handoff's pixel spec (assets pre-rendered at 1x by
 * scripts/render_pixels.mjs, displayed at 2x, pixelArt on).
 *
 * World behaviour is the compiled timeline of release 0002 — the logged
 * First Contact set on loop. Round phases: the three acts idle in their
 * studios with the lines they actually wrote. Between rounds: a LISTENING
 * EVENT — one act walks studio → corridor → archive, the camera glides and
 * follows, the walked path is paper dashes, the building dims except the
 * archive and the walked corridor, the turntable lamp lights with three
 * dotted sound rings, and on needle-up the logged influence edge is shown.
 * Every word on screen comes from the log; the world only stages it.
 */

import { CAMERA_MARGIN, cameraBounds, clampMidpoint } from "@/lib/world/camera";
import { setNow } from "@/lib/world/now";
import type { WorldTarget } from "@/lib/world/resolve";
import { CHARACTER_RESOLVE } from "@/lib/world/resolve";
import {
  clock,
  type ListeningEvent,
  type RoundEvent,
  type WorldActId,
  type WorldTimeline,
} from "@/lib/world/timeline";

const T = 16;
const WORLD_W = 33 * T; // 528
const WORLD_H = 34 * T; // 544
const ZOOM = 2;

/** Spritesheet row per character (render_pixels.mjs CHARACTERS order). */
const SHEET_ROW: Record<string, number> = {
  evers: 0, roan: 1, delta: 2, producer: 3, critic: 4, listener: 5, muse: 6,
};
const DIR_COL: Record<string, number> = { down: 0, left: 1, right: 2, up: 3 };

/** Design placements (pixelspec DEFAULT_PLACEMENTS): sprite drawn at (tx*16, ty*16 - 6). */
const PLACEMENTS: Record<string, { tx: number; ty: number; dir: string }> = {
  keep: { tx: 5, ty: 7, dir: "up" },
  rust: { tx: 15.5, ty: 7, dir: "down" },
  silt: { tx: 24.5, ty: 7, dir: "down" },
  producer: { tx: 5, ty: 22, dir: "up" },
  critic: { tx: 10.4, ty: 18.4, dir: "down" },
  listener: { tx: 4.4, ty: 26.2, dir: "down" },
  muse: { tx: 2, ty: 23.4, dir: "left" },
};

/** Studio door column per act (single-tile door gaps at y=11). */
const STUDIO_DOOR_X: Record<WorldActId, number> = { keep: 6, rust: 16, silt: 26 };
const STUDIO_NAME: Record<WorldActId, string> = { keep: "a", rust: "b", silt: "c" };
const ACT_ACCENT: Record<WorldActId, string> = { keep: "#a34c2e", rust: "#71917d", silt: "#bd9040" };
const ACT_INITIALS: Record<WorldActId, string> = { keep: "EL", rust: "RP", silt: "DM" };

/** Where a listening act stands at the turntable (design 1b: Evers at 21.4, 24.6, facing up). */
const TURNTABLE_STAND = { tx: 21.4, ty: 24.6 };
const PLATTER = { x: 21 * T + 15, y: 22 * T + 14 };
const HOME_CENTER: WorldTarget = { tx: 16.5, ty: 17 };

export interface WorldHandle {
  flyTo(target: WorldTarget): void;
  /** Camera home for the current route; null = whole-building view. */
  setAnchor(target: WorldTarget | null, fly?: boolean): void;
  destroy(): void;
}

export interface WorldOptions {
  onNavigate(route: string): void;
  era?: "A" | "B";
}

interface Bubble {
  el: HTMLDivElement;
}

export async function createWorld(
  container: HTMLElement,
  opts: WorldOptions,
): Promise<WorldHandle> {
  const Ph = (await import("phaser")).default;
  const era = opts.era === "B" ? "B" : "A";

  let timeline: WorldTimeline | null = null;
  try {
    const res = await fetch("/api/timeline");
    if (res.ok) timeline = (await res.json()) as WorldTimeline;
  } catch {
    /* the building still stands with no timeline */
  }

  // ——— DOM overlay (crisp text; the canvas never draws type) ———
  const overlay = document.createElement("div");
  overlay.className = "world-overlay";
  const camLayer = document.createElement("div");
  camLayer.className = "world-camera-layer";
  overlay.appendChild(camLayer);
  const caption = document.createElement("div");
  caption.className = "world-caption";
  overlay.appendChild(caption);

  // Camera-mode chip (bottom-left, log-line register): follow ↔ roam.
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "world-chip mono";
  overlay.appendChild(chip);
  const setChip = (mode: "follow" | "roam") => {
    chip.textContent = mode === "follow" ? "● FOLLOWING — click to roam" : "○ ROAMING — click to follow";
    chip.setAttribute("aria-pressed", String(mode === "roam"));
  };
  setChip("follow");
  const pulseChip = () => {
    chip.classList.remove("pulse");
    void chip.offsetWidth; // restart the animation
    chip.classList.add("pulse");
  };

  // Zoom steps (bottom-right): 2× / 3×, nearest-neighbour either way.
  const zoomBox = document.createElement("div");
  zoomBox.className = "world-zoom";
  const zoomOut = document.createElement("button");
  zoomOut.type = "button";
  zoomOut.className = "mono";
  zoomOut.textContent = "−";
  zoomOut.setAttribute("aria-label", "Zoom out");
  const zoomIn = document.createElement("button");
  zoomIn.type = "button";
  zoomIn.className = "mono";
  zoomIn.textContent = "+";
  zoomIn.setAttribute("aria-label", "Zoom in");
  zoomBox.append(zoomOut, zoomIn);
  overlay.appendChild(zoomBox);

  container.appendChild(overlay);

  const eraCaption = timeline
    ? `ERA ${timeline.era} · SET ${timeline.set} · ` +
      (timeline.condition === "contact"
        ? "RECORDED TOGETHER — EACH ACT COULD HEAR THE OTHERS"
        : timeline.condition.toUpperCase())
    : "ERA 2020s · THE UNIVERSE";
  const setCaption = (text: string, tone: "normal" | "lamp" | "oxide" = "normal") => {
    caption.textContent = text;
    caption.style.color =
      tone === "lamp" ? "rgba(224,178,90,0.8)" : tone === "oxide" ? "#c0663f" : "rgba(214,207,188,0.55)";
  };
  setCaption(eraCaption);

  const el = (cls: string, style: Partial<CSSStyleDeclaration>, text?: string) => {
    const d = document.createElement("div");
    d.className = cls;
    Object.assign(d.style, style);
    if (text) d.textContent = text;
    camLayer.appendChild(d);
    return d;
  };

  // Room labels on the wall caps (design frame 1a positions, world px × ZOOM).
  const roomLabels: Record<string, HTMLDivElement> = {
    a: el("world-roomlabel", { left: "70px", top: "70px" }, "STUDIO A · EVERS LANE"),
    b: el("world-roomlabel", { left: "390px", top: "70px" }, "STUDIO B · ROAN PATINA"),
    c: el("world-roomlabel", { left: "710px", top: "70px" }, "STUDIO C · DELTA MARLOWE"),
    office: el("world-roomlabel", { left: "70px", top: "492px" }, "THE OFFICE"),
    archive: el("world-roomlabel", { left: "486px", top: "492px" }, "THE ARCHIVE — LISTENING ROOM"),
  };

  // Speech bubbles: one per act (near their studio) + one at the turntable.
  const bubbleStyle: Partial<CSSStyleDeclaration> = { maxWidth: "230px" };
  const bubbles: Record<WorldActId, Bubble> & { turntable: Bubble } = {
    keep: { el: el("world-bubble", { ...bubbleStyle, left: "120px", top: "296px" }) },
    rust: { el: el("world-bubble", { ...bubbleStyle, left: "420px", top: "296px" }) },
    silt: { el: el("world-bubble", { ...bubbleStyle, left: "706px", top: "296px", maxWidth: "260px" }) },
    turntable: { el: el("world-bubble", { left: "500px", top: "846px", maxWidth: "300px" }) },
  };
  const setBubble = (
    b: Bubble,
    text: string | null,
    o: { accent?: string; opacity?: number; prefix?: string } = {},
  ) => {
    const node = b.el;
    if (!text) {
      node.style.display = "none";
      return;
    }
    node.style.display = "block";
    node.textContent = o.prefix ? `${o.prefix}  ${text}` : text;
    node.style.borderLeft = o.accent ? `2px solid ${o.accent}` : "none";
    node.style.opacity = String(o.opacity ?? 1);
  };

  // ——— the scene ———
  let handleFly: (t: WorldTarget) => void = () => {};
  let handleAnchor: (t: WorldTarget | null, fly?: boolean) => void = () => {};

  class WorldScene extends Ph.Scene {
    chars: Record<string, InstanceType<typeof Ph.GameObjects.Sprite>> = {};
    dim!: InstanceType<typeof Ph.GameObjects.Graphics>;
    litMask!: InstanceType<typeof Ph.GameObjects.Graphics>;
    fx!: InstanceType<typeof Ph.GameObjects.Graphics>; // path dashes + rings + platter light
    anchor: WorldTarget | null = null;
    eventIndex = 0;
    ringPhase = 0;
    listening = false;
    /** follow = the scripted camera owns the view; roam = the user does. */
    camMode: "follow" | "roam" = "follow";
    /** The walker the scripted camera would be following right now. */
    followTarget: InstanceType<typeof Ph.GameObjects.Sprite> | null = null;
    /** Set once a pointer-down has moved far enough to count as a drag. */
    dragging = false;
    dragDist = 0;

    /**
     * Clamp-and-set scroll through the pure camera math. Clamps the camera
     * MIDPOINT, never raw scrollX/Y: Phaser's scroll values are offset from
     * the view origin by `canvas·(1 − 1/zoom)/2` once zoomed, so clamping
     * them directly shifts (rail open) or empties (wide canvas) the pan
     * range. `centerOn` converts the clamped midpoint back for us.
     */
    scrollBy(dx: number, dy: number) {
      const cam = this.cameras.main;
      const next = clampMidpoint(
        cam.midPoint.x + dx,
        cam.midPoint.y + dy,
        cam.width / cam.zoom,
        cam.height / cam.zoom,
        WORLD_W,
        WORLD_H,
        CAMERA_MARGIN,
      );
      cam.centerOn(next.x, next.y);
    }

    /**
     * Camera bounds from the CURRENT canvas size — called at create, on
     * every scale resize (window resize AND rail toggle, via WorldPane's
     * ResizeObserver → game.scale.resize), and through zoom tweens.
     */
    applyCameraBounds() {
      const cam = this.cameras.main;
      const b = cameraBounds(cam.width / cam.zoom, cam.height / cam.zoom, WORLD_W, WORLD_H, CAMERA_MARGIN);
      cam.setBounds(b.x, b.y, b.w, b.h);
    }

    /** User interaction takes the camera: stop follows/pans, flip the chip. */
    detachCamera() {
      const cam = this.cameras.main;
      cam.stopFollow();
      cam.panEffect.reset();
      if (this.camMode !== "roam") {
        this.camMode = "roam";
        setChip("roam");
      }
    }

    /** Chip click while roaming: glide back to the scripted view. */
    resumeFollow() {
      this.camMode = "follow";
      setChip("follow");
      const cam = this.cameras.main;
      const target = this.followTarget;
      if (target) {
        cam.pan(target.x, target.y, 700, "Sine.easeOut", false, (_c: unknown, progress: number) => {
          if (progress === 1 && this.camMode === "follow" && this.followTarget) {
            cam.startFollow(this.followTarget, true, 0.08, 0.08);
          }
        });
      } else {
        const home = this.anchor ?? HOME_CENTER;
        cam.pan(home.tx * T, home.ty * T, 700, "Sine.easeOut");
      }
    }

    preload() {
      this.load.image("bg-a", "/world/bg-era-a.png");
      this.load.image("bg-b", "/world/bg-era-b.png");
      this.load.spritesheet("chars", "/world/characters.png", { frameWidth: 16, frameHeight: 16 });
    }

    create() {
      this.add.image(0, 0, era === "B" ? "bg-b" : "bg-a").setOrigin(0, 0);

      // Idle/walk animations per character row + direction.
      for (const [sprite, row] of Object.entries(SHEET_ROW)) {
        for (const [dir, col] of Object.entries(DIR_COL)) {
          const f = row * 12 + col * 3;
          this.anims.create({
            key: `${sprite}-idle-${dir}`,
            frames: [f, f, f, f + 1, f, f, f, f + 2].map((frame) => ({ key: "chars", frame })),
            frameRate: 1.6,
            repeat: -1,
          });
          this.anims.create({
            key: `${sprite}-walk-${dir}`,
            frames: [f + 1, f, f + 2, f].map((frame) => ({ key: "chars", frame })),
            frameRate: 7,
            repeat: -1,
          });
        }
      }

      for (const [id, place] of Object.entries(PLACEMENTS)) {
        const entry = CHARACTER_RESOLVE[id];
        const sprite = entry.sprite!;
        const s = this.add
          .sprite(place.tx * T, place.ty * T - 6, "chars", SHEET_ROW[sprite] * 12 + DIR_COL[place.dir] * 3)
          .setOrigin(0, 0)
          .setDepth(10);
        s.play(`${sprite}-idle-${place.dir}`);
        s.setInteractive({ useHandCursor: true });
        s.on("pointerup", () => {
          if (!this.dragging) opts.onNavigate(entry.route);
        });
        this.chars[id] = s;
      }

      // Dim overlay with an inverted mask: the lit region stays bright.
      this.litMask = this.make.graphics();
      this.dim = this.add.graphics().setDepth(20);
      this.fx = this.add.graphics().setDepth(30);

      // Bounds include the roaming margin of night void around the building
      // and follow the canvas: the rail toggle and window resizes both land
      // here as scale resize events.
      this.cameras.main.setZoom(ZOOM);
      this.applyCameraBounds();
      this.scale.on("resize", () => this.applyCameraBounds());
      this.cameras.main.centerOn(HOME_CENTER.tx * T, HOME_CENTER.ty * T);
      this.cameras.main.setBackgroundColor("#0e1013");

      // A deliberate click (rail link / sprite) is user intent: the camera
      // goes there and stays in follow, whatever mode it was in.
      handleFly = (target) => {
        this.cameras.main.stopFollow();
        this.cameras.main.panEffect.reset();
        if (this.camMode !== "follow") {
          this.camMode = "follow";
          setChip("follow");
        }
        this.cameras.main.pan(target.tx * T, target.ty * T, 700, "Sine.easeOut");
      };
      handleAnchor = (target, fly = true) => {
        this.anchor = target;
        if (fly) handleFly(target ?? HOME_CENTER);
      };

      // ——— free camera: drag / trackpad-wheel roaming ———
      this.input.on("pointerdown", () => {
        this.dragging = false;
        this.dragDist = 0;
      });
      this.input.on("pointermove", (p: { isDown: boolean; x: number; y: number; prevPosition: { x: number; y: number } }) => {
        if (!p.isDown) return;
        const dx = p.x - p.prevPosition.x;
        const dy = p.y - p.prevPosition.y;
        this.dragDist += Math.hypot(dx, dy);
        if (this.dragDist < 4) return; // still a click, not a drag
        this.dragging = true;
        this.detachCamera();
        const z = this.cameras.main.zoom;
        this.scrollBy(-dx / z, -dy / z);
      });
      this.input.on(
        "wheel",
        (_p: unknown, _over: unknown, deltaX: number, deltaY: number) => {
          this.detachCamera();
          const z = this.cameras.main.zoom;
          this.scrollBy(deltaX / z, deltaY / z);
        },
      );

      chip.onclick = () => {
        if (this.camMode === "roam") this.resumeFollow();
        else this.detachCamera();
      };
      const setZoomLevel = (level: 2 | 3) => {
        // the view size changes with the zoom: keep the bounds in step
        // through the tween, not just at its end
        this.cameras.main.zoomTo(level, 250, "Sine.easeOut", false, () => this.applyCameraBounds());
        zoomIn.disabled = level === 3;
        zoomOut.disabled = level === 2;
      };
      zoomIn.onclick = () => setZoomLevel(3);
      zoomOut.onclick = () => setZoomLevel(2);
      zoomOut.disabled = true;

      this.events.on("postupdate", () => {
        // worldView is the world-space rect actually on screen (zoom-aware);
        // the overlay is authored in 2× px, so extra zoom scales it up.
        const cam = this.cameras.main;
        const view = cam.worldView;
        camLayer.style.transform =
          `translate(${-view.x * cam.zoom}px, ${-view.y * cam.zoom}px) scale(${cam.zoom / ZOOM})`;
      });

      if (timeline && timeline.events.length > 0) this.runEvent(0);
      else this.showIdleLines();
    }

    /** No timeline (fetch failed): everyone just works. */
    showIdleLines() {
      for (const act of ["keep", "rust", "silt"] as WorldActId[]) {
        setBubble(bubbles[act], "in the studio", {
          accent: ACT_ACCENT[act],
          prefix: ACT_INITIALS[act],
          opacity: 0.45,
        });
      }
      setNow(null);
    }

    runEvent(index: number) {
      if (!timeline) return;
      this.eventIndex = index;
      const ev = timeline.events[index];
      const next = () => this.runEvent((index + 1) % timeline!.events.length);
      if (ev.kind === "round") this.runRound(ev, next);
      else this.runListening(ev, next);
    }

    runRound(ev: RoundEvent, done: () => void) {
      for (const act of ["keep", "rust", "silt"] as WorldActId[]) {
        this.time.delayedCall(300 + 400 * ["keep", "rust", "silt"].indexOf(act), () => {
          setBubble(bubbles[act], ev.lines[act], { accent: ACT_ACCENT[act], prefix: ACT_INITIALS[act] });
        });
      }
      setCaption(eraCaption);
      setNow("EL · RP · DM — recording, each alone");
      this.time.delayedCall(ev.duration * 1000, done);
    }

    /** Waypoints (in sprite coords) for an act's walk studio → turntable. */
    walkPath(actor: WorldActId): { tx: number; ty: number }[] {
      const start = PLACEMENTS[actor];
      const doorX = STUDIO_DOOR_X[actor];
      return [
        { tx: start.tx, ty: start.ty },
        { tx: doorX - 0.4, ty: start.ty },
        { tx: doorX - 0.4, ty: 13 },
        { tx: 21.9, ty: 13 },
        { tx: 21.9, ty: 16.2 },
        { tx: TURNTABLE_STAND.tx, ty: TURNTABLE_STAND.ty },
      ];
    }

    /** Tween a sprite along waypoints with walk anims; returns total ms. */
    walkAlong(
      id: string,
      sprite: string,
      path: { tx: number; ty: number }[],
      onDone: () => void,
    ): number {
      const s = this.chars[id];
      const SPEED = 4.2; // tiles per second (time-compressed ambience)
      let total = 0;
      const legs: { x: number; y: number; ms: number; dir: string }[] = [];
      for (let i = 1; i < path.length; i++) {
        const a = path[i - 1];
        const b = path[i];
        const d = Math.hypot(b.tx - a.tx, b.ty - a.ty);
        const dir =
          Math.abs(b.tx - a.tx) >= Math.abs(b.ty - a.ty)
            ? b.tx > a.tx ? "right" : "left"
            : b.ty > a.ty ? "down" : "up";
        legs.push({ x: b.tx * T, y: b.ty * T - 6, ms: (d / SPEED) * 1000, dir });
        total += (d / SPEED) * 1000;
      }
      const step = (i: number) => {
        if (i >= legs.length) {
          onDone();
          return;
        }
        const leg = legs[i];
        s.play(`${sprite}-walk-${leg.dir}`, true);
        this.tweens.add({
          targets: s,
          x: leg.x,
          y: leg.y,
          duration: leg.ms,
          ease: "Linear",
          onComplete: () => step(i + 1),
        });
      };
      step(0);
      return total;
    }

    drawPathDashes(actor: WorldActId) {
      const doorX = STUDIO_DOOR_X[actor];
      // Tile-centre dash path, the design's register (1b: paper dashes every 6px).
      const pts = [
        [doorX + 0.5, 12],
        [doorX + 0.5, 13.5],
        [22.5, 13.5],
        [22.5, 16],
        [22.2, 21.5],
      ];
      this.fx.fillStyle(0xa9a290, 0.5);
      for (let i = 0; i < pts.length - 1; i++) {
        const [ax, ay] = pts[i];
        const [bx, by] = pts[i + 1];
        const n = Math.round((Math.hypot(bx - ax, by - ay) * T) / 6);
        for (let k = 0; k < n; k++) {
          this.fx.fillRect(
            Math.round((ax + ((bx - ax) * k) / n) * T),
            Math.round((ay + ((by - ay) * k) / n) * T),
            2,
            2,
          );
        }
      }
    }

    /** The three dotted sound rings off the platter (radii 15/22/30 at 1x). */
    drawRings(phase: number) {
      const spec: [number, number][] = [
        [15, 10],
        [22, 14],
        [30, 18],
      ];
      // platter label lights lamp-colour
      this.fx.fillStyle(0xe0b25a, 1);
      this.fx.fillCircle(PLATTER.x, PLATTER.y, 3);
      spec.forEach(([r, stepDeg], i) => {
        const alpha = 0.45 + 0.4 * Math.sin(phase * 2.6 - i * 1.1);
        this.fx.fillStyle(0xe0b25a, Math.max(0.15, alpha));
        for (let a = 0; a < 360; a += stepDeg) {
          const x = Math.round(PLATTER.x + r * Math.cos((a * Math.PI) / 180));
          const y = Math.round(PLATTER.y + r * Math.sin((a * Math.PI) / 180));
          this.fx.fillRect(x, y, 1, 1);
        }
      });
    }

    setDim(on: boolean, actor: WorldActId | null) {
      this.dim.clear();
      this.dim.clearMask();
      if (!on || !actor) return;
      const doorX = STUDIO_DOOR_X[actor];
      this.litMask.clear();
      this.litMask.fillStyle(0xffffff, 1);
      // archive + its walls, and the walked corridor strip (design pixel.js clip rects)
      this.litMask.fillRect(14 * T, 15 * T, 18 * T, 18 * T);
      const x1 = Math.min(doorX - 1.5, 20.5);
      const x2 = Math.max(doorX + 1.5, 24);
      this.litMask.fillRect(x1 * T, 11 * T, (x2 - x1) * T, 5 * T);
      const mask = this.litMask.createGeometryMask();
      mask.invertAlpha = true;
      this.dim.setMask(mask);
      this.dim.fillStyle(0x07090d, 0.45); // the handoff's user-set default dim
      this.dim.fillRect(0, 0, WORLD_W, WORLD_H);
    }

    runListening(ev: ListeningEvent, done: () => void) {
      const actor = ev.actor;
      const sprite = CHARACTER_RESOLVE[actor].sprite!;
      const s = this.chars[actor];
      const out = this.walkPath(actor);
      const back = [...out].reverse();
      const cam = this.cameras.main;

      // away lines dim, they don't disappear; the actor's studio reads empty
      setBubble(bubbles[actor], `studio ${STUDIO_NAME[actor]} — empty`, { opacity: 0.45 });
      for (const other of ["keep", "rust", "silt"] as WorldActId[]) {
        if (other !== actor) bubbles[other].el.style.opacity = "0.4";
      }

      // camera glide, then follow the walker (never hard-cuts) — unless the
      // user is roaming: then the chip pulses and the camera stays theirs.
      this.followTarget = s;
      if (this.camMode === "follow") {
        cam.stopFollow();
        cam.pan(s.x, s.y, 700, "Sine.easeOut", false, (_c: unknown, progress: number) => {
          if (progress === 1 && this.camMode === "follow") cam.startFollow(s, true, 0.08, 0.08);
        });
      } else {
        pulseChip();
      }

      this.drawPathDashes(actor);
      setNow(`${ACT_INITIALS[actor]} · walking to the archive`);

      const walkMs = this.walkAlong(actor, sprite, out, () => {
        // needle down
        s.play(`${sprite}-idle-up`);
        this.listening = true;
        this.setDim(true, actor);
        roomLabels.archive.classList.add("lit");
        setBubble(bubbles.turntable, ev.logLine, { accent: "#e0b25a" });
        setCaption(
          `${clock(ev.t + walkMs / 1000)} · NEEDLE DOWN — THIS IS THE ONLY WAY AN ACT HEARS ANOTHER`,
          "lamp",
        );
        setNow(`${ACT_INITIALS[actor]} · needle down in the archive`);

        const dwellMs = Math.max(6000, ev.duration * 1000 - 2 * walkMs - 1500);
        this.time.delayedCall(dwellMs, () => {
          // needle up: the influence edge is written
          this.listening = false;
          this.fx.clear();
          this.setDim(false, null);
          roomLabels.archive.classList.remove("lit");
          setBubble(bubbles.turntable, null);
          setCaption(
            `${clock(ev.t + (walkMs + dwellMs) / 1000)} · ON NEEDLE-UP, AN EDGE IS WRITTEN: ${ev.edgeLine}`,
            "oxide",
          );

          this.walkAlong(actor, sprite, back, () => {
            const home = PLACEMENTS[actor];
            s.play(`${sprite}-idle-${home.dir}`);
            for (const other of ["keep", "rust", "silt"] as WorldActId[]) {
              bubbles[other].el.style.opacity = "1";
            }
            this.followTarget = null;
            if (this.camMode === "follow") {
              cam.stopFollow();
              const target = this.anchor ?? HOME_CENTER;
              cam.pan(target.tx * T, target.ty * T, 800, "Sine.easeOut");
            }
            this.time.delayedCall(600, done);
          });
        });
      });
    }

    update(time: number) {
      if (this.listening) {
        this.fx.clear();
        // dashes persist under the rings while the record plays
        const ev = timeline?.events[this.eventIndex];
        if (ev && ev.kind === "listening") this.drawPathDashes(ev.actor);
        this.drawRings(time / 1000);
      }
    }
  }

  const game = new Ph.Game({
    type: Ph.CANVAS,
    parent: container,
    width: container.clientWidth || 640,
    height: container.clientHeight || 640,
    backgroundColor: "#0e1013",
    pixelArt: true,
    scene: WorldScene,
  });

  const observer = new ResizeObserver(() => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w > 0 && h > 0) game.scale.resize(w, h);
  });
  observer.observe(container);

  return {
    flyTo: (target) => handleFly(target),
    setAnchor: (target, fly) => handleAnchor(target, fly),
    destroy: () => {
      observer.disconnect();
      game.destroy(true);
      overlay.remove();
      setNow(null);
    },
  };
}
