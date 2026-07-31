"use client";

/**
 * The left pane: Archive Row as a Phaser 3 world — the AFAR house on its
 * street corner, the road, and the four resident buildings facing it —
 * built from the design handoff's pixel spec (assets pre-rendered at 1x
 * by scripts/render_pixels.mjs, displayed at 2x, pixelArt on). Building
 * occupancy is DATA: /api/street resolves lease / move-in ready /
 * occupied from the agents' building metadata, and the occupancy layer is
 * painted at runtime with the same parity-gated painters the pipeline
 * uses. Residents idle in their rooms under name plates — no logged
 * lines, no speech.
 *
 * The staff animate from logged rows only: the Producer walks the
 * direction (the previous boundary's logged brief) office → each studio
 * at set start; post-set the Critic walks the per-act verdicts to each
 * studio, the Listener takes the archive armchair with the reaction, and
 * the Muse leaves the next theme at the window. A resident's listening
 * event (street door → lamp crossing → the archive; the block dims except
 * archive + crossing + their building) stages only from logged resident
 * perceptions — none exist yet, so the machinery waits.
 *
 * The world has two ways of being watched (lib/world/mode.ts owns the
 * pure state). NOW — the default: the acts potter in their studios
 * (ambient idle, small non-claiming movements, their last logged lines
 * dimmed), the latest record sits on the shelf at the turntable, and
 * clicking it (or the rail control) plays that block's staging once; a
 * live-poll arrival stages "A NEW RECORD JUST LANDED", plays the new
 * block once, and settles back to idle. REPLAY: the compiled catalogue —
 * every published set played chronologically (0002 → 0003 → 0004 →
 * repeat) on one continuous clock, with a rail picker that jumps the
 * loop to any block's start.
 *
 * Round phases: the three acts idle in their studios with the lines they
 * actually wrote. In CONTACT sets, between rounds: a LISTENING EVENT — one
 * act walks studio → corridor → archive, the camera glides and follows,
 * the walked path is paper dashes, the building dims except the archive
 * and the walked corridor, the turntable lamp lights with three dotted
 * sound rings, and on needle-up the logged influence edge is shown. In
 * ISOLATION sets the doors stay closed — nobody walks, nobody listens,
 * because nobody heard anybody; that is the condition. Between set-blocks
 * a transition beat announces the next record. Every word on screen comes
 * from the log; the world only stages it.
 */

import { CAMERA_MARGIN, cameraBounds, clampMidpoint } from "@/lib/world/camera";
import {
  BUBBLES,
  buildingLabelPx,
  DASHES,
  DIM,
  HOME_CENTER,
  officeToArchiveChairPath,
  officeToStudioPath,
  PLACEMENTS,
  PLATTER,
  readyInterior,
  ROOM_LABELS,
  SHEET_ROW,
  STREET_BUILDINGS,
  streetDimRects,
  streetWalkPath,
  STUDIO_DOOR_X,
  STUDIO_NAME,
  studioToStudioPath,
  studioToTurntablePath,
  tenantInterior,
  tenantStand,
  TILE,
  WORLD_H,
  WORLD_W,
  type StreetBuilding,
  type TenantProp,
} from "@/lib/world/geometry";
// The same painters the asset pipeline uses (world_parity-gated): the
// street's occupancy layer is painted at runtime from live agents data.
import { eraPal, paintBuildingState } from "@/lib/world/pixelpaint.mjs";
import {
  buildingLabelText,
  resolveBuildings,
  type BuildingState,
} from "@/lib/world/residents";
import {
  onCommand,
  publishRailState,
  type WorldCommand,
} from "@/lib/world/control";
import {
  arrivalCaption,
  arrivalNowLine,
  diffCatalogue,
  splicePlayOrder,
  startTimelinePoller,
} from "@/lib/world/live";
import {
  advanceOnce,
  arrivalPlayOrder,
  beginOnce,
  blockPlayOrder,
  blockStartIndex,
  idleCaption,
  idleNowLine,
  initialPhase,
  lastLoggedLines,
  latestBlockIndex,
  modeOf,
  pickerEntries,
  shelfLine,
  type ModePhase,
} from "@/lib/world/mode";
import { setNow } from "@/lib/world/now";
import type { WorldTarget } from "@/lib/world/resolve";
import { CHARACTER_RESOLVE } from "@/lib/world/resolve";
import {
  clock,
  type BriefEvent,
  type DirectionDeliveredEvent,
  type ListeningEvent,
  type ReactionEvent,
  type RoundEvent,
  type SetBlockMeta,
  type StreetListeningEvent,
  type TransitionEvent,
  type VerdictDeliveredEvent,
  type WorldActId,
  type WorldCatalogue,
} from "@/lib/world/timeline";

// All geometry (canvas dims, placements, doors, turntable, labels, walk
// waypoints, dim rects) comes from the registry via lib/world/geometry.ts.
const T = TILE;
const ZOOM = 2;

const DIR_COL: Record<string, number> = { down: 0, left: 1, right: 2, up: 3 };

const ACTS: readonly WorldActId[] = ["keep", "rust", "silt"];
const STAFF: readonly string[] = ["producer", "critic", "listener", "muse"];

const ACT_ACCENT: Record<WorldActId, string> = { keep: "#a34c2e", rust: "#71917d", silt: "#bd9040" };
const ACT_INITIALS: Record<WorldActId, string> = { keep: "EL", rust: "RP", silt: "DM" };
/** Staff bubble register: the office grey, initials like the acts'. */
const STAFF_ACCENT = "#8b8577";
const STAFF_INITIALS: Record<string, string> = { producer: "PR", critic: "CR", listener: "LS", muse: "MU" };

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

  let timeline: WorldCatalogue | null = null;
  try {
    // no-store: the timeline is dynamic now (publishes land in Neon's
    // timeline_source row); a browser-cached hour-old copy had the world
    // looping a stale catalogue after a publish.
    const res = await fetch("/api/timeline", { cache: "no-store" });
    if (res.ok) timeline = (await res.json()) as WorldCatalogue;
  } catch {
    /* the building still stands with no timeline */
  }

  // Archive Row occupancy: who lives where, from the agents' building
  // metadata (/api/street: Neon when reachable, fixtures otherwise). The
  // fallback is the unassigned street — FOR LEASE papered over, designed
  // rooms move-in ready — so the block stands with zero env.
  let streetStates: BuildingState[] = resolveBuildings(STREET_BUILDINGS, []);
  try {
    const res = await fetch("/api/street", { cache: "no-store" });
    if (res.ok) {
      const data = (await res.json()) as { buildings?: BuildingState[] };
      if (
        Array.isArray(data.buildings) &&
        data.buildings.every((b) => typeof b?.id === "string" && typeof b?.status === "string")
      ) {
        streetStates = data.buildings;
      }
    }
  } catch {
    /* the street stands as designed */
  }
  const stateById = new Map(streetStates.map((s) => [s.id, s]));

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

  // Per-block caption: which record is playing, its era, and — plain
  // language — what the acts could hear while making it.
  const blockCaption = (block: number) => {
    const b = timeline?.blocks[block];
    return b
      ? `${b.catalogueNo} · ERA ${b.era} · SET ${b.set} · ${b.conditionLine}`
      : "ERA 2020s · THE UNIVERSE";
  };
  const setCaption = (text: string, tone: "normal" | "lamp" | "oxide" = "normal") => {
    caption.textContent = text;
    caption.style.color =
      tone === "lamp" ? "rgba(224,178,90,0.8)" : tone === "oxide" ? "#c0663f" : "rgba(214,207,188,0.55)";
  };
  setCaption(blockCaption(0));

  const el = (cls: string, style: Partial<CSSStyleDeclaration>, text?: string) => {
    const d = document.createElement("div");
    d.className = cls;
    Object.assign(d.style, style);
    if (text) d.textContent = text;
    camLayer.appendChild(d);
    return d;
  };

  // Room labels on the wall caps (registry positions: design frame 1a, world px × ZOOM).
  const roomLabels: Record<string, HTMLDivElement> = Object.fromEntries(
    Object.entries(ROOM_LABELS).map(([key, label]) => [
      key,
      el("world-roomlabel", { left: `${label.px[0]}px`, top: `${label.px[1]}px` }, label.text),
    ]),
  );

  // Archive Row name plates, same register, derived from each shell: the
  // resident's name when occupied, FOR LEASE / MOVE-IN READY otherwise.
  // Residents idle without speech — the tunz roster has no logged lines,
  // and the world never invents one; the plate is what the street says.
  for (const building of STREET_BUILDINGS) {
    const state = stateById.get(building.id);
    if (!state) continue;
    const [lx, ly] = buildingLabelPx(building);
    el("world-roomlabel", { left: `${lx}px`, top: `${ly}px` }, buildingLabelText(state));
  }

  // Speech bubbles: one per act (near their studio), the turntable log
  // line, the archive armchair (the Listener's seat), the office window
  // (the Muse's spot).
  const bubbles = Object.fromEntries(
    Object.entries(BUBBLES).map(([key, b]) => [
      key,
      { el: el("world-bubble", { left: `${b.px[0]}px`, top: `${b.px[1]}px`, maxWidth: `${b.maxWidth}px` }) },
    ]),
  ) as Record<WorldActId, Bubble> & { turntable: Bubble; archiveChair: Bubble; window: Bubble };
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
  let handleCatalogue: (next: WorldCatalogue) => void = () => {};
  let handleCommand: (cmd: WorldCommand) => void = () => {};

  class WorldScene extends Ph.Scene {
    chars: Record<string, InstanceType<typeof Ph.GameObjects.Sprite>> = {};
    /** Resident sprites by building id (occupied Archive Row rooms only). */
    residents: Record<string, InstanceType<typeof Ph.GameObjects.Sprite>> = {};
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
     * Live splice (lib/world/live.ts): after the poller spots new blocks,
     * this queue overrides the natural event order for one pass — the
     * current block finishes, the arrivals play, the old order resumes.
     */
    pendingOrder: number[] = [];
    /** A restructured catalogue waits here and is adopted at wrap-around. */
    pendingCatalogue: WorldCatalogue | null = null;
    /** NOW / REPLAY (lib/world/mode.ts): the default is NOW, idle. */
    phase: ModePhase = initialPhase();
    /** An arrival that landed mid-once-through; staged when it ends. */
    pendingArrival: { arrivals: SetBlockMeta[]; firstNew: number } | null = null;
    /** Bumped on every startAmbience so stale idle timers go quiet. */
    ambienceSeq = 0;

    /** The next REPLAY event to play: the splice queue first, else natural order. */
    nextEventIndex(): number {
      const shifted = this.pendingOrder.shift();
      if (shifted !== undefined) return shifted;
      const next = (this.eventIndex + 1) % (timeline?.events.length || 1);
      if (next === 0 && this.pendingCatalogue) {
        // a reshaped catalogue (re-published run) is adopted only here, on
        // the wrap — never mid-sequence, never as a restart
        timeline = this.pendingCatalogue;
        this.pendingCatalogue = null;
      }
      return next;
    }

    /**
     * A new record just landed: in follow mode the camera gives a brief
     * acknowledging beat toward the archive (where records live) and
     * returns — unless it is following a walker, which is never cut.
     * Roaming users only get the caption and the chip pulse: no yanks.
     */
    acknowledgeArrival() {
      if (this.camMode !== "follow" || this.followTarget) {
        pulseChip();
        return;
      }
      const cam = this.cameras.main;
      cam.pan(PLATTER.x, PLATTER.y, 700, "Sine.easeOut");
      this.time.delayedCall(2400, () => {
        if (this.camMode !== "follow" || this.followTarget) return;
        const home = this.anchor ?? HOME_CENTER;
        cam.pan(home.tx * T, home.ty * T, 800, "Sine.easeOut");
      });
    }

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

      // The street's occupancy layer, painted from live agents data with
      // the SAME parity-gated painters the asset pipeline uses: lease
      // rooms papered over, ready rooms with dust ghosts, occupied rooms
      // fitted per the tenant system (one accent + one prop).
      const states = this.textures.createCanvas("street-states", WORLD_W, WORLD_H);
      if (states) {
        const ctx = states.getContext();
        const pal = eraPal(era);
        for (const building of STREET_BUILDINGS) {
          const state = stateById.get(building.id);
          if (!state) continue;
          const interior =
            state.status === "occupied"
              ? tenantInterior(building, {
                  accent: state.accent,
                  accentD: state.accentD,
                  prop: state.prop as TenantProp | null,
                })
              : state.status === "ready"
                ? readyInterior(building)
                : [];
          paintBuildingState(ctx, building, pal, { status: state.status, interior }, era);
        }
        states.refresh();
        this.add.image(0, 0, "street-states").setOrigin(0, 0).setDepth(5);
      }

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

      // Residents: one sprite per OCCUPIED building, idling at the tenant
      // stand (the design's resident silhouette — flat cap, chest stripe).
      for (const building of STREET_BUILDINGS) {
        const state = stateById.get(building.id);
        if (!state || state.status !== "occupied") continue;
        const stand = tenantStand(building);
        const s = this.add
          .sprite(stand.tx * T, stand.ty * T - 6, "chars", SHEET_ROW.vess * 12 + DIR_COL.up * 3)
          .setOrigin(0, 0)
          .setDepth(10);
        s.play("vess-idle-up");
        this.residents[building.id] = s;
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

      // The poller found a fresh catalogue: diff it against what is
      // playing and splice — the clock never resets, the current block is
      // never interrupted (lib/world/live.ts owns the pure math).
      handleCatalogue = (nextCat) => {
        if (!timeline) {
          // the initial fetch had failed: the world finally gets a timeline
          timeline = nextCat;
          if (nextCat.events.length > 0) this.enterIdle();
          return;
        }
        const diff = diffCatalogue(timeline, nextCat);
        if (diff.kind === "noop") return;

        if (this.phase.kind === "replay") {
          if (diff.kind === "restructured") {
            this.pendingCatalogue = nextCat; // adopted at the next wrap-around
            return;
          }
          const firstNewEventIndex = timeline.events.length;
          timeline = nextCat; // changed display facts apply in place
          if (diff.newBlockIndices.length > 0) {
            this.pendingCatalogue = null;
            this.pendingOrder = splicePlayOrder(nextCat.events, this.eventIndex, firstNewEventIndex);
            const arrivals = diff.newBlockIndices.map((i) => nextCat.blocks[i]);
            setCaption(arrivalCaption(arrivals), "lamp");
            setNow(arrivalNowLine(arrivals));
            this.acknowledgeArrival();
          } else if (nextCat.events[this.eventIndex]?.kind === "round") {
            // e.g. a title updated by the Critic, refreshed mid-round
            setCaption(blockCaption(nextCat.events[this.eventIndex].block));
          }
          this.publishRail();
          return;
        }

        // NOW mode. Idle means nothing is playing, so even a restructured
        // catalogue can be adopted on the spot; a once-through in progress
        // is never interrupted — arrivals and reshapes wait for its end.
        if (diff.kind === "restructured") {
          if (this.phase.kind === "idle") {
            timeline = nextCat;
            this.enterIdle(); // re-stage the shelf with the fresh catalogue
          } else {
            this.pendingCatalogue = nextCat;
          }
          return;
        }
        const firstNewEventIndex = timeline.events.length;
        timeline = nextCat; // changed display facts apply in place
        if (diff.newBlockIndices.length > 0) {
          const arrivals = diff.newBlockIndices.map((i) => nextCat.blocks[i]);
          if (this.phase.kind === "idle") {
            this.stageArrival(arrivals, firstNewEventIndex);
          } else {
            this.pendingArrival = { arrivals, firstNew: firstNewEventIndex };
          }
        } else if (this.phase.kind === "idle") {
          this.enterIdle(); // display facts changed; refresh the idle labels
        }
        this.publishRail();
      };

      // Rail controls: the NOW/REPLAY toggle, the shelf play, the picker.
      handleCommand = (cmd) => {
        if (!timeline || timeline.events.length === 0) return;
        if (cmd.kind === "mode") {
          if (cmd.mode === modeOf(this.phase)) return;
          if (cmd.mode === "replay") {
            this.enterReplay(0);
          } else {
            this.resetStage();
            this.pendingOrder = [];
            if (this.pendingCatalogue) {
              timeline = this.pendingCatalogue;
              this.pendingCatalogue = null;
            }
            this.enterIdle();
          }
        } else if (cmd.kind === "play-latest") {
          if (this.phase.kind === "idle") this.playLatestOnce();
        } else if (cmd.kind === "jump") {
          const start = blockStartIndex(timeline.events, cmd.block);
          if (start >= 0) this.enterReplay(start);
        }
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

      // The shelf: clicking the turntable while the world idles plays the
      // latest record's staging once. (A drag never counts as a click.)
      const shelf = this.add
        .zone(PLATTER.x - 30, PLATTER.y - 26, 60, 52)
        .setOrigin(0, 0)
        .setInteractive({ useHandCursor: true });
      shelf.on("pointerup", () => {
        if (!this.dragging && this.phase.kind === "idle") this.playLatestOnce();
      });

      // Default on load: NOW — the acts are in the studio.
      if (timeline && timeline.events.length > 0) this.enterIdle();
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

    /**
     * Publish what the rail's controls need: mode, the picker entries,
     * the shelf record, and (in replay) the block currently playing.
     */
    publishRail() {
      if (!timeline || timeline.blocks.length === 0) {
        publishRailState(null);
        return;
      }
      publishRailState({
        mode: modeOf(this.phase),
        entries: pickerEntries(timeline),
        latest: latestBlockIndex(timeline),
        playingBlock:
          this.phase.kind === "replay" ? (timeline.events[this.eventIndex]?.block ?? null) : null,
      });
    }

    /**
     * Stop everything scripted and put the stage back: timers and tweens
     * killed, acts home at their consoles, lights up, turntable quiet. In
     * follow mode the camera glides home; a roaming camera stays put.
     */
    resetStage() {
      this.time.removeAllEvents();
      this.tweens.killAll();
      this.listening = false;
      this.fx.clear();
      this.applyDim(null);
      roomLabels.archive.classList.remove("lit");
      this.followTarget = null;
      for (const id of [...ACTS, ...STAFF]) {
        const s = this.chars[id];
        const home = PLACEMENTS[id];
        s.setPosition(home.tx * T, home.ty * T - 6);
        s.play(`${CHARACTER_RESOLVE[id].sprite!}-idle-${home.dir}`);
      }
      for (const act of ACTS) bubbles[act].el.style.opacity = "1";
      for (const [buildingId, s] of Object.entries(this.residents)) {
        const building = STREET_BUILDINGS.find((b) => b.id === buildingId)!;
        const stand = tenantStand(building);
        s.setPosition(stand.tx * T, stand.ty * T - 6);
        s.play("vess-idle-up");
      }
      setBubble(bubbles.turntable, null);
      setBubble(bubbles.archiveChair, null);
      setBubble(bubbles.window, null);
      if (this.camMode === "follow") {
        const cam = this.cameras.main;
        cam.stopFollow();
        cam.panEffect.reset();
        const home = this.anchor ?? HOME_CENTER;
        cam.pan(home.tx * T, home.ty * T, 700, "Sine.easeOut");
      }
    }

    /**
     * NOW, idle: the acts are in the studio. Their last logged lines show
     * dimmed (remembered, not claimed), the latest record sits on the
     * shelf, and the ambience timer gives the rooms small honest life.
     * The camera is never moved by idle.
     */
    enterIdle() {
      this.phase = { kind: "idle" };
      this.pendingArrival = null;
      if (!timeline || timeline.events.length === 0) {
        this.showIdleLines();
        this.publishRail();
        return;
      }
      const lines = lastLoggedLines(timeline);
      for (const act of ACTS) {
        setBubble(bubbles[act], lines?.[act] ?? "in the studio", {
          accent: ACT_ACCENT[act],
          prefix: ACT_INITIALS[act],
          opacity: 0.45,
        });
      }
      setBubble(bubbles.turntable, shelfLine(timeline), { accent: "#e0b25a", opacity: 0.75 });
      setCaption(idleCaption(timeline));
      setNow(idleNowLine(timeline));
      this.startAmbience();
      this.publishRail();
    }

    /** REPLAY: the catalogue loop, from `startIndex` (0 = the top). */
    enterReplay(startIndex: number) {
      this.resetStage();
      this.pendingOrder = [];
      this.pendingArrival = null;
      this.ambienceSeq++; // idle timers go quiet
      this.phase = { kind: "replay" };
      this.runEvent(startIndex);
    }

    /** The shelf click / rail control: the latest record's staging, once. */
    playLatestOnce() {
      if (!timeline) return;
      const { phase, first } = beginOnce(
        blockPlayOrder(timeline.events, latestBlockIndex(timeline)),
        "record",
      );
      if (first === null) return;
      this.resetStage();
      this.phase = phase;
      this.publishRail();
      this.runEvent(first);
    }

    /**
     * A new record just landed while the world idled: the arrival staging
     * runs (lamp caption, NOW line, the camera's acknowledging beat), then
     * the new block plays once, then idle resumes with it as latest.
     */
    stageArrival(arrivals: SetBlockMeta[], firstNew: number) {
      if (!timeline) return;
      const order = arrivalPlayOrder(timeline.events, firstNew);
      this.resetStage();
      setCaption(arrivalCaption(arrivals), "lamp");
      setNow(arrivalNowLine(arrivals));
      this.acknowledgeArrival();
      const { phase, first } = beginOnce(order, "arrival");
      this.phase = phase;
      this.publishRail();
      if (first === null) {
        this.enterIdle();
        return;
      }
      // let the caption and the camera beat land before the record starts
      this.time.delayedCall(3200, () => this.runEvent(first));
    }

    /** A once-through ended: stage what queued behind it, else go idle. */
    finishOnce() {
      if (this.pendingArrival) {
        const p = this.pendingArrival;
        this.pendingArrival = null;
        this.stageArrival(p.arrivals, p.firstNew);
        return;
      }
      if (this.pendingCatalogue) {
        timeline = this.pendingCatalogue;
        this.pendingCatalogue = null;
      }
      this.enterIdle();
    }

    /**
     * Idle ambience: every few seconds one act shifts at the console,
     * turns toward the shelf, or takes a step in place — existing frames,
     * no claims, no dialogue, and never the camera. The office joins in
     * occasionally (a staff member shifts at their desk, now that the
     * staff have real walk frames), and so does an occupied resident room
     * across the street. Randomized cadence; `ambienceSeq` retires stale
     * timers when the phase changes.
     */
    startAmbience() {
      const seq = ++this.ambienceSeq;
      const tick = () => {
        if (seq !== this.ambienceSeq || this.phase.kind !== "idle") return;
        const roll = Math.random();
        const residentIds = Object.keys(this.residents);
        if (roll < 0.6 || (roll < 0.85 && residentIds.length === 0)) {
          this.idleGesture(ACTS[Math.floor(Math.random() * ACTS.length)]);
        } else if (roll < 0.85) {
          this.residentGesture(residentIds[Math.floor(Math.random() * residentIds.length)]);
        } else {
          this.idleGesture(STAFF[Math.floor(Math.random() * STAFF.length)]);
        }
        this.time.delayedCall(3500 + Math.random() * 5500, tick);
      };
      this.time.delayedCall(1200 + Math.random() * 2400, tick);
    }

    idleGesture(id: string) {
      const s = this.chars[id];
      const sprite = CHARACTER_RESOLVE[id].sprite!;
      const home = PLACEMENTS[id];
      const settle = (ms: number) =>
        this.time.delayedCall(ms, () => {
          if (this.followTarget !== s) s.play(`${sprite}-idle-${home.dir}`);
        });
      const roll = Math.random();
      if (roll < 0.4) {
        // turn toward the shelf (some other way), then back to the console
        const dirs = (["down", "left", "right", "up"] as const).filter((d) => d !== home.dir);
        s.play(`${sprite}-idle-${dirs[Math.floor(Math.random() * dirs.length)]}`);
        settle(1400 + Math.random() * 1400);
      } else if (roll < 0.7) {
        // a step in place at the console (walk frames, no displacement)
        s.play(`${sprite}-walk-${home.dir}`);
        settle(650);
      } else {
        // a small shift aside and back
        const dx = (Math.random() < 0.5 ? -1 : 1) * 4;
        s.play(`${sprite}-walk-${dx < 0 ? "left" : "right"}`);
        this.tweens.add({
          targets: s,
          x: s.x + dx,
          duration: 420,
          yoyo: true,
          ease: "Sine.easeInOut",
          onComplete: () => {
            if (this.followTarget !== s) s.play(`${sprite}-idle-${home.dir}`);
          },
        });
      }
    }

    /** A resident's ambience: a turn at the console, then back. No words —
     * their rooms carry name plates, not bubbles, until lines are logged. */
    residentGesture(buildingId: string) {
      const s = this.residents[buildingId];
      if (!s || this.followTarget === s) return;
      const dirs = ["down", "left", "right"] as const;
      s.play(`vess-idle-${dirs[Math.floor(Math.random() * dirs.length)]}`);
      this.time.delayedCall(1200 + Math.random() * 1600, () => {
        if (this.followTarget !== s) s.play("vess-idle-up");
      });
    }

    runEvent(index: number) {
      if (!timeline) return;
      this.eventIndex = index;
      const ev = timeline.events[index];
      if (!ev) return;
      const next = () => {
        if (this.phase.kind === "once") {
          const { phase, next: n } = advanceOnce(this.phase);
          this.phase = phase;
          if (n === null) this.finishOnce();
          else this.runEvent(n);
        } else if (this.phase.kind === "replay") {
          this.runEvent(this.nextEventIndex());
        }
        // idle: a stray completion after a phase change stages nothing
      };
      if (this.phase.kind === "replay") this.publishRail();
      if (ev.kind === "round") this.runRound(ev, next);
      else if (ev.kind === "listening") this.runListening(ev, next);
      else if (ev.kind === "direction_delivered") this.runDirection(ev, next);
      else if (ev.kind === "verdict_delivered") this.runVerdict(ev, next);
      else if (ev.kind === "reaction") this.runReaction(ev, next);
      else if (ev.kind === "brief") this.runBrief(ev, next);
      else if (ev.kind === "street_listening") this.runStreetListening(ev, next);
      else this.runTransition(ev, next);
    }

    /** The beat between set-blocks: the building rests, the next record is announced. */
    runTransition(ev: TransitionEvent, done: () => void) {
      for (const act of ["keep", "rust", "silt"] as WorldActId[]) {
        bubbles[act].el.style.opacity = "0.4";
      }
      setBubble(bubbles.turntable, null);
      setCaption(`${clock(ev.t)} · ${ev.caption}`, "lamp");
      setNow(ev.nowLine);
      this.time.delayedCall(ev.duration * 1000, () => {
        for (const act of ["keep", "rust", "silt"] as WorldActId[]) {
          bubbles[act].el.style.opacity = "1";
        }
        done();
      });
    }

    runRound(ev: RoundEvent & { block: number }, done: () => void) {
      for (const act of ["keep", "rust", "silt"] as WorldActId[]) {
        this.time.delayedCall(300 + 400 * ["keep", "rust", "silt"].indexOf(act), () => {
          setBubble(bubbles[act], ev.lines[act], { accent: ACT_ACCENT[act], prefix: ACT_INITIALS[act] });
        });
      }
      setCaption(blockCaption(ev.block));
      const b = timeline?.blocks[ev.block];
      const who =
        b?.condition === "isolation"
          ? "EL · RP · DM — recording alone, doors closed"
          : "EL · RP · DM — recording, each in their studio";
      setNow(b ? `${b.catalogueNo} · ${who}` : who);
      this.time.delayedCall(ev.duration * 1000, done);
    }

    /** Waypoints (in sprite coords) for an act's walk studio → turntable (registry). */
    walkPath(actor: WorldActId): { tx: number; ty: number }[] {
      return studioToTurntablePath(actor);
    }

    /**
     * Attach the scripted camera to a walker (glide, then follow — never a
     * hard cut); a roaming user just gets the chip pulse, no yanks.
     */
    followWalker(s: InstanceType<typeof Ph.GameObjects.Sprite>) {
      this.followTarget = s;
      if (this.camMode === "follow") {
        const cam = this.cameras.main;
        cam.stopFollow();
        cam.pan(s.x, s.y, 700, "Sine.easeOut", false, (_c: unknown, progress: number) => {
          if (progress === 1 && this.camMode === "follow" && this.followTarget === s) {
            cam.startFollow(s, true, 0.08, 0.08);
          }
        });
      } else {
        pulseChip();
      }
    }

    /** The walk is over: release the camera back to the route anchor. */
    releaseWalker() {
      this.followTarget = null;
      if (this.camMode === "follow") {
        const cam = this.cameras.main;
        cam.stopFollow();
        const home = this.anchor ?? HOME_CENTER;
        cam.pan(home.tx * T, home.ty * T, 800, "Sine.easeOut");
      }
    }

    /** Tween a sprite along waypoints with walk anims; returns total ms. */
    walkAlong(
      s: InstanceType<typeof Ph.GameObjects.Sprite>,
      sprite: string,
      path: { tx: number; ty: number }[],
      onDone: () => void,
    ): number {
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

    /** Paper-coloured 2px dashes every 6px along tile-centre points (design 1b). */
    drawDashes(pts: [number, number][]) {
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

    drawPathDashes(actor: WorldActId) {
      const doorX = STUDIO_DOOR_X[actor];
      // Tile-centre dash path, the design's register (1b: paper dashes every 6px).
      this.drawDashes([
        [doorX + DASHES.doorOffset, DASHES.startY],
        [doorX + DASHES.doorOffset, DASHES.cornerY],
        ...DASHES.tail,
      ]);
    }

    /** A street listening's dashes: the resident's walked path itself. */
    drawStreetDashes(building: StreetBuilding) {
      this.drawDashes(streetWalkPath(building).map((p): [number, number] => [p.tx, p.ty]));
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

    /** Dim the whole block except the given lit rects (tiles: x, y, w, h);
     * null lifts the dim. The handoff's user-set default opacity, 0.45. */
    applyDim(litRects: [number, number, number, number][] | null) {
      this.dim.clear();
      this.dim.clearMask();
      if (!litRects) return;
      this.litMask.clear();
      this.litMask.fillStyle(0xffffff, 1);
      for (const [x, y, w, h] of litRects) this.litMask.fillRect(x * T, y * T, w * T, h * T);
      const mask = this.litMask.createGeometryMask();
      mask.invertAlpha = true;
      this.dim.setMask(mask);
      this.dim.fillStyle(0x07090d, 0.45); // the handoff's user-set default dim
      this.dim.fillRect(0, 0, WORLD_W, WORLD_H);
    }

    setDim(on: boolean, actor: WorldActId | null) {
      if (!on || !actor) {
        this.applyDim(null);
        return;
      }
      // archive + its walls, and the walked corridor strip (registry dim rects)
      const doorX = STUDIO_DOOR_X[actor];
      const x1 = Math.min(doorX - DIM.corridor.halfWidth, DIM.corridor.span[0]);
      const x2 = Math.max(doorX + DIM.corridor.halfWidth, DIM.corridor.span[1]);
      this.applyDim([
        DIM.archive,
        [x1, DIM.corridor.y, x2 - x1, DIM.corridor.h],
      ]);
    }

    runListening(ev: ListeningEvent & { block: number }, done: () => void) {
      const cat = timeline?.blocks[ev.block]?.catalogueNo ?? "";
      const actor = ev.actor;
      const sprite = CHARACTER_RESOLVE[actor].sprite!;
      const s = this.chars[actor];
      const out = this.walkPath(actor);
      const back = [...out].reverse();

      // away lines dim, they don't disappear; the actor's studio reads empty
      setBubble(bubbles[actor], `studio ${STUDIO_NAME[actor]} — empty`, { opacity: 0.45 });
      for (const other of ["keep", "rust", "silt"] as WorldActId[]) {
        if (other !== actor) bubbles[other].el.style.opacity = "0.4";
      }

      // camera glide, then follow the walker (never hard-cuts) — unless the
      // user is roaming: then the chip pulses and the camera stays theirs.
      this.followWalker(s);

      this.drawPathDashes(actor);
      setNow(`${cat} · ${ACT_INITIALS[actor]} — walking to the archive`);

      const walkMs = this.walkAlong(s, sprite, out, () => {
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
        setNow(`${cat} · ${ACT_INITIALS[actor]} — needle down in the archive`);

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

          this.walkAlong(s, sprite, back, () => {
            const home = PLACEMENTS[actor];
            s.play(`${sprite}-idle-${home.dir}`);
            for (const other of ["keep", "rust", "silt"] as WorldActId[]) {
              bubbles[other].el.style.opacity = "1";
            }
            this.releaseWalker();
            this.time.delayedCall(600, done);
          });
        });
      });
    }

    /**
     * SET START (design + logged brief): the Producer walks office →
     * each studio in turn and delivers the session's direction — the
     * previous boundary's logged theme — as a brief line at each door.
     */
    runDirection(ev: DirectionDeliveredEvent & { block: number }, done: () => void) {
      const cat = timeline?.blocks[ev.block]?.catalogueNo ?? "";
      const s = this.chars.producer;
      setCaption(`${clock(ev.t)} · SET START — THE PRODUCER WALKS THE DIRECTION TO THE STUDIOS`, "lamp");
      setNow(`${cat} · PR — delivering the direction`);
      this.followWalker(s);
      const stops: WorldActId[] = ["keep", "rust", "silt"];
      const visit = (i: number) => {
        if (i >= stops.length) {
          const back = [...officeToStudioPath(PLACEMENTS.producer, stops[stops.length - 1])].reverse();
          this.walkAlong(s, "producer", back, () => {
            s.play(`producer-idle-${PLACEMENTS.producer.dir}`);
            this.releaseWalker();
            this.time.delayedCall(400, done);
          });
          return;
        }
        const act = stops[i];
        const path =
          i === 0
            ? officeToStudioPath(PLACEMENTS.producer, act)
            : studioToStudioPath(stops[i - 1], act);
        this.walkAlong(s, "producer", path, () => {
          s.play("producer-idle-up");
          setBubble(bubbles[act], ev.line, { accent: STAFF_ACCENT, prefix: STAFF_INITIALS.producer });
          this.time.delayedCall(2400, () => {
            setBubble(bubbles[act], null);
            visit(i + 1);
          });
        });
      };
      visit(0);
    }

    /**
     * POST-SET: the Critic walks to each reviewed act's studio and
     * delivers the logged verdict to their face (excerpted at compile).
     */
    runVerdict(ev: VerdictDeliveredEvent & { block: number }, done: () => void) {
      const cat = timeline?.blocks[ev.block]?.catalogueNo ?? "";
      const s = this.chars.critic;
      const stops = (["keep", "rust", "silt"] as WorldActId[]).filter((act) => ev.reviews[act]);
      if (stops.length === 0) {
        done();
        return;
      }
      setCaption(`${clock(ev.t)} · THE CRITIC DELIVERS THE VERDICTS — TO THEIR FACES`, "oxide");
      setNow(`${cat} · CR — delivering the verdicts`);
      this.followWalker(s);
      const visit = (i: number) => {
        if (i >= stops.length) {
          const back = [...officeToStudioPath(PLACEMENTS.critic, stops[stops.length - 1])].reverse();
          this.walkAlong(s, "critic", back, () => {
            s.play(`critic-idle-${PLACEMENTS.critic.dir}`);
            this.releaseWalker();
            this.time.delayedCall(400, done);
          });
          return;
        }
        const act = stops[i];
        const path =
          i === 0
            ? officeToStudioPath(PLACEMENTS.critic, act)
            : studioToStudioPath(stops[i - 1], act);
        this.walkAlong(s, "critic", path, () => {
          s.play("critic-idle-up");
          setBubble(bubbles[act], ev.reviews[act]!, { accent: STAFF_ACCENT, prefix: STAFF_INITIALS.critic });
          this.time.delayedCall(3000, () => {
            setBubble(bubbles[act], null);
            visit(i + 1);
          });
        });
      };
      visit(0);
    }

    /**
     * POST-SET: the Listener walks to the archive's armchair and reacts —
     * the logged reaction, excerpted, from the cheap seats.
     */
    runReaction(ev: ReactionEvent & { block: number }, done: () => void) {
      const cat = timeline?.blocks[ev.block]?.catalogueNo ?? "";
      const s = this.chars.listener;
      const out = officeToArchiveChairPath(PLACEMENTS.listener);
      const back = [...out].reverse();
      setCaption(`${clock(ev.t)} · THE LISTENER TAKES THE ARCHIVE ARMCHAIR`, "normal");
      setNow(`${cat} · LS — reacting from the cheap seats`);
      this.followWalker(s);
      const walkMs = this.walkAlong(s, "listener", out, () => {
        s.play("listener-idle-down");
        setBubble(bubbles.archiveChair, ev.line, { accent: STAFF_ACCENT, prefix: STAFF_INITIALS.listener });
        const dwellMs = Math.max(4000, ev.duration * 1000 - 2 * walkMs - 1000);
        this.time.delayedCall(dwellMs, () => {
          setBubble(bubbles.archiveChair, null);
          this.walkAlong(s, "listener", back, () => {
            s.play(`listener-idle-${PLACEMENTS.listener.dir}`);
            this.releaseWalker();
            this.time.delayedCall(400, done);
          });
        });
      });
    }

    /**
     * POST-SET: the Muse at the office window with the next brief's theme
     * — the world outside enters through the brief, never the ear.
     */
    runBrief(ev: BriefEvent & { block: number }, done: () => void) {
      setCaption(`${clock(ev.t)} · THE MUSE LEAVES THE NEXT THEME AT THE WINDOW`, "lamp");
      setNow(`next theme: ${ev.theme}`);
      setBubble(bubbles.window, ev.line, { accent: STAFF_ACCENT, prefix: STAFF_INITIALS.muse });
      this.time.delayedCall(ev.duration * 1000, () => {
        setBubble(bubbles.window, null);
        done();
      });
    }

    /**
     * A resident's listening event (design 2b): out their own door, across
     * at the lamp, through the AFAR street door into the archive; the
     * whole block dims except the archive, the crossing strip, and their
     * building. Staged only from LOGGED resident perceptions — and only a
     * building the data actually occupies stages the walk; otherwise the
     * archive alone tells the story.
     */
    runStreetListening(ev: StreetListeningEvent & { block: number }, done: () => void) {
      const cat = timeline?.blocks[ev.block]?.catalogueNo ?? "";
      const building = STREET_BUILDINGS.find((b) => b.id === ev.building);
      if (!building) {
        done();
        return;
      }
      const s = this.residents[ev.building] ?? null;
      setCaption(
        `${clock(ev.t)} · AN ARTIST CROSSES TO THE ARCHIVE — THE ONLY LISTENING ROOM ON THE STREET`,
        "lamp",
      );
      setNow(`${cat} · ${ev.residentName} — crossing to the archive`);

      const beginListen = (walkMs: number) => {
        this.listening = true;
        this.applyDim(streetDimRects(building));
        roomLabels.archive.classList.add("lit");
        setBubble(bubbles.turntable, ev.logLine, { accent: "#e0b25a" });
        setNow(`${cat} · ${ev.residentName} — needle down in the archive`);
        const dwellMs = Math.max(6000, ev.duration * 1000 - 2 * walkMs - 1500);
        this.time.delayedCall(dwellMs, () => {
          this.listening = false;
          this.fx.clear();
          this.applyDim(null);
          roomLabels.archive.classList.remove("lit");
          setBubble(bubbles.turntable, null);
          if (!s) {
            done();
            return;
          }
          const back = [...streetWalkPath(building)].reverse();
          this.walkAlong(s, "vess", back, () => {
            const stand = tenantStand(building);
            s.setPosition(stand.tx * T, stand.ty * T - 6);
            s.play("vess-idle-up");
            this.releaseWalker();
            this.time.delayedCall(600, done);
          });
        });
      };

      if (!s) {
        beginListen(0);
        return;
      }
      this.followWalker(s);
      this.drawStreetDashes(building);
      const out = streetWalkPath(building);
      const walkMs = this.walkAlong(s, "vess", out, () => {
        s.play("vess-idle-left");
        beginListen(walkMs);
      });
    }

    update(time: number) {
      if (this.listening) {
        this.fx.clear();
        // dashes persist under the rings while the record plays
        const ev = timeline?.events[this.eventIndex];
        if (ev && ev.kind === "listening") this.drawPathDashes(ev.actor);
        else if (ev && ev.kind === "street_listening") {
          const building = STREET_BUILDINGS.find((b) => b.id === ev.building);
          if (building && this.residents[ev.building]) this.drawStreetDashes(building);
        }
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

  // Liveness: while the tab is open the world refetches the timeline on a
  // slow jittered cadence (paused when hidden) and splices new releases
  // into the playing loop — no refresh, ever. Failures are silent.
  const stopPolling = startTimelinePoller({
    fetchCatalogue: async () => {
      const res = await fetch("/api/timeline", { cache: "no-store" });
      return res.ok ? ((await res.json()) as WorldCatalogue) : null;
    },
    onCatalogue: (cat) => handleCatalogue(cat),
    doc: document,
  });

  // Rail controls (NOW/REPLAY toggle, shelf play, release picker) arrive
  // over the control bus; the scene answers with its rail state.
  const offCommand = onCommand((cmd) => handleCommand(cmd));

  return {
    flyTo: (target) => handleFly(target),
    setAnchor: (target, fly) => handleAnchor(target, fly),
    destroy: () => {
      stopPolling();
      offCommand();
      publishRailState(null);
      observer.disconnect();
      game.destroy(true);
      overlay.remove();
      setNow(null);
    },
  };
}
