---
name: llaves-bracket
description: How the /llaves knockout bracket visualization is built — the radial
  oval (ellipse) SVG tree of the World Cup knockouts drawn in vanilla JS, its per-phase
  circles/flags, the "explode" separation between wings, and the calibrated 16avos
  spacing. Use whenever working on the llaves / bracket / eliminatorias / árbol radial /
  óvalo view, the circle sizes per phase, the ellipse shape, the flag rings, the
  spacing between matches/groups/top-bottom/left-right, the predicted advancer
  flags / advancing chain, or the geometry-check script.
---

# llaves-bracket

The `/<slug>/llaves/` page draws the knockout bracket as a **vertical oval
(ellipse) tree** in SVG with vanilla JS (no React, no d3). Each match is a pair
of circles (the two teams' flags); winners advance inward toward the final at
the center. Slots without a real result show the **player's predicted
advancer** as a faded flag (opacity 0.28) and their predicted score; real
results replace them at full opacity.

## Files

| File | Role |
|------|------|
| `static/llaves.js` | All geometry + rendering. The heart of the view. |
| `pool/services/llaves.py` | `build_bracket(user, quiniela)` → JSON payload: 16 LAST_32 matches (tree order) + `tree` of real/predicted advancers. |
| `pool/services/bracket.py` | Shared KO helpers: `winner_team`, `SOURCE_RE` (`W##`/`L##` placeholders). |
| `pool/tests/test_llaves.py` | In-memory tests of the advancing chain (`_advancers`). |
| `templates/llaves.html` | Shell: `#bracket-svg` (with `data-copa`), `{{ bracket\|json_script:"bracket-data" }}`, floating back button. |
| `.claude/llaves_geom_check.mjs` | **Dev-only** headless geometry check (no DOM): measures overlaps, spacings and the bbox. Run with `node`. |

Data flow: `views` → `build_bracket(user, quiniela)` →
`json_script#bracket-data` → `llaves.js` reads/parses it on `DOMContentLoaded`
→ `computeLayout()` → `render()`.

## Data side (`pool/services/llaves.py`)

`build_bracket(user, quiniela)` returns `{ "matches": [...16...], "tree": {...} }`.

**`matches`** — the 16 LAST_32 matches. The **order** is what `llaves.js`'s
wing layout consumes — derived from the real tree by walking `W##`
placeholders from the final down to the leaves (`_leaf_order`), so adjacent
pairs feed the same octavos. Each match dict: `home`/`away` (`{id, name,
flag_url, code}` or placeholder text + empty flag), `played`, `home_goals`,
`away_goals`, `winner`, and `pred` (the player's prediction: `home_goals`,
`away_goals`, `winner` = who they pass to octavos, or `null`).

**`tree`** — advancers for the scoreless deeper phases, aligned with the 4
groups-of-4 of the layout: `cuartos[i]` (group Gi) has `octavos` (2 slots →
the cuarto's 2 circles) and `cuarto` (1 slot → a semifinal circle);
`semis[k]` fills a final circle; `final` is just a score. Each **slot** is
`{real, pred, score}`: the real advancer of that node's match, the predicted
one, and the score to paint over its pair (real if `FINISHED`, else the
player's, via `_score`).

### The advancing chain (`_advancers` / `_pred_pick`)

Per node, `_advancers` returns `(real, predicted)` advancer. The contender
feeding each slot is the child's **real winner when known, falling back to
the child's predicted advancer** — this re-anchoring is load-bearing:
predictions are captured against the real teams (`save_prediction` validates
`advancing_team` against `match.home_team_id`/`away_team_id`), so
interpreting them against the fantasy chain paints wrong flags and breaks
the penalty-pick match-up. `_pred_pick` resolves one prediction: higher
goals → that contender; draw → `advancing_team` if it equals a contender;
otherwise `None` (chain broken → empty circle). Covered by
`pool/tests/test_llaves.py`.

**Flags are HD here only.** `_team()` builds `flags_80/{flag_code}.webp` (80px)
*for this view*; the rest of the project uses `Team.flag_path` = `flags_40/...png`.
Don't "unify" them — llaves wants the sharper webp.

## Geometry model (`static/llaves.js`)

The whole layout is a set of **concentric vertical ellipses**, one per phase.
A match's two circles sit on the ellipse with their **midpoint on the curve**,
separated by `±(L/2)·tangent` — so every match in a phase has the exact same
separator length `L[phase]`, while the oval elongates to use mobile height.

### Constants (top of the IIFE) — the tuning surface

```js
var CX = 192, CY = 345;          // center
var AX = 170, AY = 280;          // semi-axes of the OUTER ellipse (16avos)
var K   = [1.0, 0.74, 0.49, 0.20]; // ellipse scale per phase: 16avos, oct, cuartos, semis
var L   = [34, 40, 46, 50, 76];  // pair separator per phase (+ final)
var RAD = [14, 16, 18, 20, 23];  // circle radius per phase (+ final)
var SEAMR = 1.18;                // base seam scale (sets `da`)
var CLUSTER = 0.103;             // tightness of the octavos-pair (intra gap = da·(1-CLUSTER))
var INTER = 1.072;               // inter-octavos-pair gap (in `da` units)
var DV = 4.5;                    // "explode" vertical  (separates top/bottom)
var DH = -2.5;                   // "explode" horizontal (<0 compresses left/right)
var FIN_DX = 0;                  // final's horizontal offset from center
```

Phase index order everywhere is **`[16avos, octavos, cuartos, semis, final]`**.

### Key concepts

- **`ept(scale, th)` / `tang(scale, th)`** — point and unit-tangent on ellipse
  `scale` (= a `K` value) at angle `th` (degrees; θ=0 right, 90 bottom, 180
  left, 270 top). `pair(scale, th, Lp)` returns the two circle centers `a`/`b`
  and `mid`.
- **Arc-length table** (`cum`, `arc2th`, `arc0`) — matches are distributed by
  **arc length** (not angle) so spacing is even on the curved oval.
- **Wings** — 4 quadrants, each 4 matches. `wings[i].start` is the cardinal
  angle; **`i` is also the "explode" group** (see below):
  `0 topL(180)`, `1 topR(270)`, `2 botR(0)`, `3 botL(90)`. The two top wings
  (0,1) feed the top semifinal; the two bottom (3,2) feed the bottom one.
  Each wing also carries **`gi`**, the tree group-of-4 (the `matches` slice
  and the `tree.cuartos[]` index) — it differs from the wing index at the
  bottom because the geometry crosses there (wing 2 ↔ G3, wing 3 ↔ G2).
  Node `side` (`home`/`away`) picks which number of the pair's `score` each
  circle shows: home = circle `b`, away = circle `a`.
- **Placement inside a wing** — `off = [0, gIntra, gIntra+gInter, 2·gIntra+gInter]`
  where `gIntra = da·(1-CLUSTER)` (the two 16avos that share an octavos, tight)
  and `gInter = da·INTER` (the "diagonal" division between the wing's two
  octavos-pairs). The remainder of the quadrant is the **seam** between wings:
  `seam = P/4 − wingSpan`.
- **`apex()` + `nudgePole()`** — octavos/cuartos are placed at the perpendicular-
  bisector apex of their two parents on the inner ellipse (equidistant, real
  distance), then nudged away from the poles so they don't bunch up.
- **Semis & final** — semis are hardcoded at the poles (θ=270 top, θ=90 bottom).
  The **final is a horizontal pair** (side by side) at the center (`FIN_DX`
  offset). Both semis' stems converge to the final's midpoint.

### The "explode" (separation between the four groups)

After building all nodes/links on the ellipse, each is shifted **rigidly by its
group** to open a horizontal channel (top/bottom) and a vertical one (left/right),
with the final fixed at the crossing center:

```js
var SHIFT = [
  {dx:-DH,dy:-DV}, {dx:DH,dy:-DV},   // wings 0,1 (top)   → up-left, up-right
  {dx:DH,dy:DV},   {dx:-DH,dy:DV},   // wings 2,3 (bottom)→ down-right, down-left
  {dx:0,dy:-DV},   {dx:0,dy:DV},     // semis: vertical only (not split sideways)
  {dx:0,dy:0},                       // final: fixed
];
```

Each **node** carries a `g` (group 0–6); each **link** carries `g1`/`g2` (its two
endpoints' groups, since a stem crosses groups, e.g. a wing's cuarto → its semi).
The shift is applied to both arrays at the end of `computeLayout`. `DV`/`DH` are
**independent** (each affects only its axis) because at a pole seam both wings
share the same `DV`, and at an equator seam both share the same `DH`.

### Calibrated 16avos separations (units)

The spacing was tuned to an explicit ratio target, in **units of the gap between
the two flags of one match** (≈6px):

| separation | knob(s) | target (u) |
|------------|---------|-----------:|
| flags of the same match | `L[0]`, `RAD[0]` (= 1 unit) | 1 |
| between matches (share octavos) | `CLUSTER` | 2.5 |
| between the two groups-of-4 (meet in cuartos) | `INTER` | 5 |
| left / right | `DH` (negative compresses) | 7.5 |
| top / bottom | `DV` | 10 |

Spreading the wing matches (bigger `INTER`/lower `CLUSTER`) also **shrinks the
seam**, which is what drives left/right & top/bottom — so those four knobs
interact through the fixed arc budget `P`. To re-target, give the desired unit
sequence and re-run the check script (below) until it matches; then transcribe
the four constants.

## Rendering (`render()` in `llaves.js`)

- Sets the SVG `viewBox` (currently `"4 45 376 601"`) — **must be re-fit** to the
  content bbox whenever geometry changes, or there's dead space / clipping. The
  check script prints a suggested viewBox.
- Draws `links` first (played matches get solid strokes, pending ones faint),
  then `nodes` (a `base-300` bg circle + glow source + `ring` + the flag
  `<image>` clipped to a circle). Flag `<image>` size derives from `n.r` →
  circles scale automatically with `RAD`.
- Per node, the flag is `n.team || n.winner` (real) or, failing that,
  `n.predWinner` painted at **opacity 0.28** (estimate). The real winner of a
  played match gets a primary ring + `#win-glow` halo (`paint()`).
- **Scores** render next to each pair on every phase that has one: real if
  played (winning side in primary), predicted in diluted `base-content`. The
  number sits on the outward perpendicular from the pair's `mid`, shifted
  `ALONG` toward its own circle.
- The only interaction: any circle with a real-or-estimated team sets
  `data-dialog-team` → opens the team dialog (global delegation in
  `team_dialog.js`). There is no side panel.
- The copa image (`data-copa` on `#bracket-svg`) is drawn between the final's
  two circles, decorative.

## Geometry-check script (tuning workflow)

`.claude/llaves_geom_check.mjs` **ports `computeLayout` without the DOM**. It
mirrors the same constants at the top; edit them, run `node
.claude/llaves_geom_check.mjs`, and read:

- the **five 16avos separations** in px and in units vs the target,
- min gap between any two circles + any **overlaps** (`gap < 3px`),
- the content **bbox** and a **suggested viewBox**.

Workflow to change sizes/spacing safely:
1. Edit the constants in the **script**, run it.
2. Iterate until spacings hit target, `solapes: 0`, and bbox looks right.
3. Copy the final constants into `static/llaves.js` and set the suggested
   `viewBox`.
4. `node --check static/llaves.js`.

Keep the script's constants in sync with `llaves.js` when documenting a new
baseline. Known drift: the script still has `L[4]=64` while `llaves.js` uses
`76` (the final's pair was widened to fit the copa) — don't copy 64 back.
The script is dev-only — it is not shipped or collected.

## Gotchas

- **Don't shrink `L[i]` below `2·RAD[i]` + a few px** — the two circles of one
  match would fuse. `L` must grow with `RAD`.
- **Radii grow toward the center**; because area ∝ r², roughly constant radius
  increments already read as an accelerating size jump — keep later increments
  gentle.
- **`AY > AX`** makes the oval taller than wide (mobile). Reducing `AY` flattens
  it; re-fit the viewBox afterward.
- **Never interpret a stored prediction against the fantasy chain.** Score
  predictions and `advancing_team` refer to the match's real slots/teams at
  capture time; `_advancers` must keep preferring the child's real winner
  over the predicted one when building contenders, or flags come out wrong
  and draw+penalty picks stop matching (see `test_llaves.py`).
- Flags come from `flags_80` **only in `llaves.py`** — see the flags note above.
