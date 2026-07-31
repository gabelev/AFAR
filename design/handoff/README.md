# Handoff: AFAR — Label Interface

## Overview
Split-screen interface for AFAR, a record label with three AI acts who make music continuously and hear each other **only** through released records. Left (~55%): a 2D top-down pixel world of the label building (Phaser 3). Right (~45%): the catalogue — player, act pages, release pages. The central dramatic event is an act walking to the archive and playing another act's record — the entire perception channel, made visible.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended look and behavior, not production code to ship. The task is to **recreate these designs in the target stack**: left pane as **Phaser 3 embedded as a React component in a Next.js app** (Tiled TMX/JSON maps + spritesheets, the Smallville architecture but NOT its art), right pane as **React + Tailwind**. `pixel.js` in this bundle is a faithful spec of the tile grid, sprites, and palette — port its data (maps, sprite pixel maps, palette, era LUT) into real Tiled maps and PNG spritesheets; do not embed it as-is.

## Fidelity
**High-fidelity.** Colors, typography, spacing, copy, and pixel art are final. Recreate pixel-perfectly. The pixel maps in `pixel.js` are the authoritative source for tiles and character sprites (render them to PNG at 1x, display at 2x/3x with nearest-neighbor).

## The World (left pane)
Canvas: 33×34 tiles, 16px base tiles, displayed at 2× (`image-rendering: pixelated` / Phaser `pixelArt: true`). Everything snaps to the tile grid.

Room rectangles (tile coords, inclusive `[x1,y1,x2,y2]`; walls fill everything else inside the shell `x1..31, y2..32`; outside is night void):
- Studio A — Evers Lane: interior `[2,3,10,10]`, concrete floor
- Studio B — Roan Patina: interior `[12,3,20,10]`, concrete floor
- Studio C — Delta Marlowe: interior `[22,3,30,10]`, concrete floor
- Corridor: `[2,12,30,14]`, floorboard
- Label office: `[2,16,13,31]`, floorboard
- Archive / listening room: `[15,16,30,31]`, floorboard; rug `[19,21,26,27]`
- Doors (single-tile gaps): studio doors at `(6,11)`, `(16,11)`, `(26,11)`; office `(7,15)`; archive `(22,15)`

Studios are isolated by default — no sightlines between them. The archive is the ONLY place one act hears another.

Room dressing (see `drawWorld`/`paint` in `pixel.js` for exact prop placement):
- Studio A (Evers, continuity): record shelf, tape-reel rack, 4-tile console, chair, two aligned crates — everything grid-straight.
- Studio B (Roan, erosion): one small desk, papers, and **dust ghosts** (dashed pale outlines) where gear was removed.
- Studio C (Delta, accumulation): console + second desk, stacked crates, cable runs across the floor, paper piles.
- Office: Producer desk (with reels + papers), Critic desk, Listener armchair + lamp, Muse standing at a window in the left wall.
- Archive: two long record shelves on the top wall, 2×2 turntable station on the rug, lamp pool, listening armchair, arrival crates by the door.

### Characters
16×16, 4-direction, 3 frames (idle / step L / step R — step frames just alternate the foot row). Pixel maps in `pixel.js` (`S` object). Silhouettes are the identity — tellable apart at 16px by shape and colour alone:
- **Evers Lane** — oxide `#a34c2e`: tall, wide brim, one unbroken column.
- **Roan Patina** — verdigris `#71917d`: hooded, tapering, pixels missing from the coat.
- **Delta Marlowe** — ochre `#bd9040`: broad, stacked, layered bands.
- Staff (grey `#8b8577`): Producer (headphones), Critic (glasses + papers), Listener (round, seated), Muse (long hair, pale robe).

Silhouette drift (act page): the sprite loses coat pixels per set — deterministic erosion of non-outline pixels (see `drawDrift`).

### The listening event (money shot)
1. Act leaves studio; camera glides (Phaser `pan`/`startFollow`, never hard-cuts).
2. Walked path shown as paper-colored 2px dashes along tile centers.
3. Whole building dims under `rgba(7,9,13,0.45)` (tweakable 0.2–0.85; **user-set default 0.45**) EXCEPT the archive room + the walked corridor strip, which stay lit.
4. Turntable label lights lamp-color; three dotted concentric sound rings (radii 15/22/30px at 1x) pulse off the platter.
5. Log line at the turntable: `EL  playing AFAR-0001 — STANDING WATER · side A`.
6. On needle-up an influence edge is written: `AFAR-0001 → Evers Lane · set 2`.

### Speech bubbles
Typewritten log lines, no bubble chrome: IBM Plex Mono 11px `#d6cfbc` on `rgba(10,11,13,0.78)`, `padding 4px 7px`, `border-left: 2px solid <act color>`, prefixed with act initials (`EL`, `RP`, `DM`). Room labels use the same backing, 10px, letter-spacing 0.22em, placed on the wall cap above each room. Away/distant lines drop to 40–45% opacity.

### Era system (runtime-generatable, no hand-drawn eras)
Everything expressible as **palette LUT + prop diff**:
- LUT (8 entries, see `eraPal('B')`): void `#0e1013→#13100b`, rain→dust (streaks vanish), glass `#31404c→#4d4026`, floorboard `#463d31→#4b4033` (+dark variant), concrete `#383b40→#3d3a33` (+dark), wall face `#4b4f57→#55503f`, lamp `#e0b25a→#d8a248`.
- Prop diff: corridor puddles −2 · archive crates +2 (sets accumulate) · Roan's studio: crate → dust ghost.
- Act accent colors NEVER remap — identity survives the season.

## Right pane (React + Tailwind)
864px reference width. Paper background `#ddd6c4`, ink `#1c1a15`, hairlines `rgba(28,26,21,0.2–0.25)`, secondary `#5e5a4f` / `#4a463c`. Player bar: 72px, `#14130f`, mono 12px. No border radius anywhere; 1px hairline rules; record-sleeve register, not SaaS.

Screens (all present in the design file):
1. **Catalogue home** (frame 1a right): AFAR wordmark 40px/700/ls 0.34em; tagline; roster table (chip 12px square, name 24px/600, stance in mono ls 0.2em act color, stance quote italic 13px, status `IN STUDIO`); latest-release card with mini graph cover; staff index; quiet player bar (`■ NOTHING PLAYING — THE BUILDING IS QUIET`).
2. **Now playing** (1b right): `● LISTENING ROOM LIVE`, title 36px/700, progress hairline w/ oxide fill, event log (mono, timestamped: 03:12 leaves Studio A / 03:14 pulls AFAR-0001 from shelf C2 / 03:15 needle down / 03:33 edge written), note: "The archive is the whole perception channel."
3. **Release page** (1c–1e — three cover registers, pick one): 480px square cover **which IS the influence graph** (etched plate / sediment bands / node-and-arc score — SVG in the design file), title, era line `ERA 2020s · SET 1 · OVERCAST, DISTANT TRAFFIC, RAIN ENDING`, interaction record rows (`EL → DM` "adding a fourth layer under what Evers left" / `DM → RP` "taking out everything Delta put in" / `EL ⟲ EL` "this is the third time we've been here"), sides list.
4. **Act page** (1f, Roan Patina): name 42px + stance + quote; silhouette-drift strip on `#16140f`; takes table (take 04 kept … take 01 heard AFAR-0000 acetate); influence in/out columns (out: `none recorded since set −2` in oxide); Critic block: "Roan Patina has been coasting for three sets."

## Interactions & Behavior
- Clicking an act/release/staff member on the right **flies the left camera** to it and centres (Phaser camera pan, ~600–800ms, ease-out). Never hard-cut.
- Log lines appear/expire with act activity; away lines dim, they don't disappear.
- Camera follows a walking act during the listening event.
- Right pane routes: `/` home, `/release/[id]`, `/act/[slug]`, `/staff/[slug]`.

## State Management
- `acts[]`: id, name, stance, accent, position (tile), activity (current log line), status (`in_studio` | `walking` | `listening`).
- `releases[]`: catalogue no., title, era, set, atmosphere line, sides, `edges[] {from, to, kind, quote, take}` — the interaction record. The cover is rendered from `edges`, never stored art.
- `listeningEvent`: `{actId, releaseId, side, startedAt}` | null — drives dimming, rings, event log, player bar.
- `era`: `{palette LUT, propDiff}` derived from logged state at runtime.

## Design Tokens
World palette (16): void `#0e1013` · rain `#1b2027` · wall cap `#1e2126` · wall face `#4b4f57` · concrete `#383b40` · floorboard `#463d31` · rug `#544130` · wood `#5c4b37` · ink `#16140f` · paper `#d6cfbc` · lamp `#e0b25a` · metal `#6a6f78` · glass `#31404c` · oxide `#a34c2e` (Evers) · verdigris `#71917d` (Roan) · ochre `#bd9040` (Delta). Act accents share chroma/lightness; only hue varies.
UI: paper `#ddd6c4`, ink `#1c1a15`, bar `#14130f`, secondary `#5e5a4f`/`#4a463c`/`#a9a290`.
Type: **Archivo** (400–700; display caps letterspaced 0.06–0.34em) + **IBM Plex Mono** (400/500; all labels, logs, catalogue numbers). No third font.
Spacing: 48px page gutters, hairline-ruled rows, no shadows, no radius.

## Assets
- No external art. All tiles/sprites are original, specified as pixel maps in `pixel.js` — export to PNG spritesheets (16px tiles; 16×16 characters; props up to 32×32) for Phaser + Tiled.
- Do NOT use or imitate LimeZu "Modern Interiors" (that is the Smallville look). Kenney CC0 acceptable for gap-filling only if restyled to this palette.
- Fonts: Google Fonts — Archivo, IBM Plex Mono.

## The Street — Archive Row (extension)
Street canvas: 56×34 tiles, same 16px grid at 2×. The AFAR house is unchanged at `[1,2,31,32]` and becomes the corner landmark; a new street door punched in its east wall at `(31,22)–(31,23)` leads straight into the archive.

Street layout (tile coords, inclusive):
- West sidewalk `[32,2,33,32]` · road `[34,2,37,32]` (dashed lane line at x=35/36) · east sidewalk `[38,2,39,32]`
- RES 01 — FOR LEASE: shell `[40,2,53,8]`, papered door `(40,5)`, papered windows `(40,3)`,`(40,7)`
- RES 02 — move-in ready: shell `[40,10,53,16]`, door `(40,13)`, windows `(40,11)`,`(40,15)`; interior holds only dust ghosts + neutral-accent console
- RES 03 — Vess Camber (first resident): shell `[40,18,53,24]`, door `(40,21)`, windows `(40,19)`,`(40,23)`; guest-violet console, amp, crates
- RES 04 — FOR LEASE: shell `[40,26,53,32]`, papered door `(40,29)`, papered windows `(40,27)`,`(40,31)`
- Furniture: lamp posts `(33,8)`,`(38,16)`,`(33,26)` (lamp-color pools) · bench `(38,24)` · mailbox `(32,20)` (demos get mailed to the label) · street trees in sidewalk pits `(32,5)`,`(38,10)`,`(32,29)`,`(38,30)` · NY subway entrance (R train, downtown) `(38,4)–(39,6)`: railed stairwell, darkening steps, globe lamp, pixel R bullet · parked cars along the west curb at `(34,8)`,`(34,17)`,`(34,25)` (1×2 tiles, muted body colors from the palette) · road puddles (era A)
- Office pets: the Critic's cat curled on the desk papers `(9.6,19.6)` · the Muse's Scottish deerhound at the window `(2.6,24.2)` (tall wiry grey, ~20×14px, `deerhound()`/`cat()` in pixel.js)

Sightline rule: every resident door faces west across the road toward the AFAR corner — the walk to the archive is legible from any front door. The archive remains the only listening room in town.

Street listening event (frame 2b): resident leaves their door, crosses at the lamp, enters the AFAR street door into the archive. Whole block dims (same tweakable dim), EXCEPT: the archive, the crossing strip (tiles `[31,19]–[39,24]`), and the resident's own building. Lamp pools stay lit. Walked path in paper-colored dashes.

Street LUT entries (era B): asphalt `#2b2e34→#302d27`, asphalt seam `#262a2f→#2a2722`, pavement `#4a463d→#4d4536`, grout `#403c34→#423b2e`, curb `#5a5449→#5c5240`. Prop diff: puddles −4, dust patches +2. Guest accents never remap.

Tenant system: a resident room is parameterized by ONE accent color (console trim, sign plate, sprite coat — guest violet `#8a6f9e`/`#5e4a6c` for Vess Camber) + ONE character-prop slot (amp, tape reels, …; dashed ghost when empty). See `drawResidentRoom(cv,{acc,accD,prop,occupied})`.

Staff sprites completed: Producer, Critic, Listener, Muse now have down/side/up maps with proper leg rows (row 14 splits into step-L/step-R walk frames, same convention as the acts). Silhouettes kept: headphones / glasses+papers / round / long hair + pale robe, staff grey `#8b8577`. Plus `vess` — the first resident sprite (flat cap, chest stripe).

## Files
- `AFAR Interface.dc.html` — the full design doc: frames 1a (normal state), 1b (listening event), 1c–1e (release-page cover registers), 1f (act page), 1g (tile palette, spritesheets, swatches), 1h (era LUT proof). Open in a browser.
- `pixel.js` — authoritative tile/sprite/palette spec: `PAL`, `eraPal()`, sprite maps `S` (acts + completed staff + vess), house layout in `grid()`/`paint()`, street layout in `streetGrid()`/`paintStreet()`/`drawStreet()`, resident rooms in `drawResidentRoom()`, era prop diffs.
- `screenshots/` — PNG captures of every frame: `1a-normal-state`, `1b-listening-event`, `1c/1d/1e` release-page cover registers, `1f-act-page-roan-patina`, `1g-asset-sheets`, `1h-era-proof`, plus street frames `2a-street-normal`, `2b-street-listening-event`, `2c-street-era-b-proof`, `2d-staff-spritesheets`, `2e-resident-interior`.
- `photos/` — press photos, one per act (`press-evers/roan/delta.png`, 960×1200): hi-res pixel portraits (72×96 grid) in contemporary clothes — Evers in a chore jacket over a white tee with headphones round his neck, Roan in an eroding oversized hoodie and cargos, Delta in a quilted puffer with a record-bag strap — on a studio backdrop with film grain and an archival paper caption. Use on act pages, press kit, socials.
