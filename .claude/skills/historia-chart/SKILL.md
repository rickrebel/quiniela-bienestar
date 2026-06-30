---
name: historia-chart
description: How the /historia progress chart is built — the cumulative-points
  line chart per player, tick by tick, in two views (an absolute (simple) fixed axis and
  the "cono"/funnel/megaphone elastic-Y view). Use whenever working on the
  history / progress / "Historia" graph, the build_progress service, progress.js
  renderer, the X-axis modes (partido/tanda/día) or the Cono/Simple switch,
  the cone / funnel view with its least-squares envelope and iso-value curves,
  the start cutoff, or its TomSelect / legend / tooltip behavior.
---

# /historia progress chart

The "Historia" page draws one line per player showing their **cumulative
points over time**. It reads frozen `ScoreSnapshot` rows, shapes them in a
Python service, embeds the JSON in the page, and renders a hand-built SVG
(no chart library) that is responsive via `ResizeObserver`.

## File map

| File | Role |
|------|------|
| `pool/views/progress.py` | `history_view`: `@login_required @with_quiniela`, calls `build_progress`, renders `historia.html`. No JSON endpoint — data is embedded. |
| `pool/services/progress.py` | `build_progress(quiniela, me)` → `{ticks, series, defaults}`. All data shaping lives here. |
| `templates/historia.html` | Page shell: TomSelect `<select>`, X-mode switch, `#history-chart`, `{{ progress|json_script:"history-data" }}`. |
| `static/progress.js` | The renderer: reads `#history-data`, builds the SVG, X-axis modes, TomSelect, legend, tooltip. |
| `assets/css/source.css` | `--chart-1..8`, `--chart-me`, `--chart-dim` tokens and all `.hist-*` / `.history-*` styles. |
| URL | `pool/urls.py`: `path("historia/", progress.history_view, name="history")`, mounted under `/<slug>/`. |

Data flow: `ScoreSnapshot` → `build_progress` → `json_script` → `progress.js`
→ SVG.

## The data contract (`build_progress`)

Returns a dict with three keys, serialized via `json_script`:

- **`ticks`**: ordered list, one per **tanda** (all matches sharing the same
  `datetime` share a tick — the cumulative is per-tanda, not per-match).
  `ticks[0]` is the synthetic origin `{"date": "", "stage": "Salida",
  "matches": [], "multiplier": 1}` so every line starts from a common zero.
  Each real tick: `{date (local ISO), stage (short_name), matches[], multiplier}`.
  `matches[]` carries FIFA codes + flag URLs for the X-axis (`_match_entry`).
- **`series`**: one per player with `has_played`. Each:
  `{id, name, virtual, me, position, points[]}` where `points[i]` is the
  cumulative at `ticks[i]` (0 where the player has no snapshot for that tick).
- **`defaults`**: preselected ids (top 1, top 2, worst real player). The
  active user (`me`) is drawn separately and never enters defaults.

`points` is filled from `ScoreSnapshot` (`user_id, match__datetime,
cumulative_points`), mapping each snapshot's datetime to its tick. Simultaneous
matches repeat the cumulative, so assigning by tick is enough.

### Start cutoff — why the chart can begin mid-tournament

`_start_cutoff(quiniela)` returns the `datetime` of the first finished match of
the **first window (by `order`) that has any `Prediction` for this quiniela**.
`build_progress` then filters finished matches to `datetime >= cutoff`.

This trims the leading flat-at-zero stretch from windows that were **born
closed**: bienestar launched at Jornada 2 (nobody predicted Jornada 1), so its
chart must start there, not at the tournament kickoff. `sanginiela`/`libres`
have predictions from their first window, so they are unchanged.

Do **not** use `Window.resolved_opens_at` as the start signal: it falls back to
the shared `Stage.opens_at`, so every group sub-window resolves a date even
when the quiniela never opened there. "Has predictions" is the discriminating
signal. The cutoff only trims a *leading* gap — a mid-tournament window with no
predictions is not skipped. See `pool/services/progress.py` and the project
CLAUDE.md note on "born closed" windows.

## The renderer (`progress.js`)

Self-invoking IIFE; bails if `#history-chart` or `#history-data` is missing.

- **Colors come from CSS variables** read once via `getComputedStyle`
  (`--chart-1..8` palette, `--chart-me`, `--chart-dim`, `--color-base-content`
  for axes). No hardcoded colors — the chart follows the daisyUI theme. Axis
  color is also written as an SVG presentation attribute so it survives a stale
  cached `tailwind.css`.
- **Three line layers** (z-order): active user (`is-me`, white + glow filter)
  at the back, then the dimmed curtain (`hist-dim`, all unselected in grey),
  then up to 8 compared players (`hist-hi`, palette colors assigned by
  selection order). `MAX_COMPARE = 8`.
- **Non-uniform X-axis (`buildCols`)**: each column's width is proportional to
  its `weight` = number of matches × the window `multiplier`. Positions come
  from a cumulative sum of weights, not equal spacing. The origin has weight 0
  (pinned to the left edge). Three X-modes toggled by `[data-xmode]` buttons:
  - `match` (default): one column per match; simultaneous matches share a tick
    → flat segment. Labels are two stacked flags (home over away).
  - `batch` ("Tanda"): one column per tick.
  - `day` ("Día"): one column per local date (aggregates ticks of that date).
- **Y-axis** (simple view): 4 grid levels; level 0 is the solid axis, the
  rest dotted so they don't read as uncolored grey lines. `maxVal` is the max
  cumulative across all series (min 1). The **cono** view replaces this with an
  elastic per-column axis — see *The Cono view* below.
- **X labels are thinned by pixel distance** (≥44px apart, first/last always),
  because unequal widths break uniform spacing.
- **Selection** via TomSelect (`remove_button` + `checkbox_options` plugins,
  accent-insensitive search). Adding/removing assigns/releases a palette slot
  (`assignColor`/`releaseColor`) and calls `refresh()` (legend + render).
  Defaults are applied as initial `items`. The control's chips are hidden and
  there is **no "N seleccionados" count** — the legend below is the reference.
- **Tooltip**: hover highlights a line and shows `name · points`; click "pins"
  a line (essential on mobile, no hover); click on empty space unpins.
- **Responsive**: `new ResizeObserver(() => render()).observe(root)` redraws on
  resize at native pixel size (no stretched viewBox). `render()` toggles
  `.is-short` on the chart when `clientHeight < 580` → CSS thins every line
  (immersive/short phones).
- **Immersive (mobile)**: `[data-immersive-open]` (button `open_in_full`,
  bottom-left, shown only ≤820px) opens a fullscreen landscape overlay
  (`body.history-immersive`); `[data-immersive-close]` (`clear`, beside the
  switch) exits. **Hybrid orientation**: tries `requestFullscreen` +
  `screen.orientation.lock("landscape")`; if unsupported (iOS) falls back to a
  CSS rotation (`body.is-rotated`, applied only while portrait, reactive to
  `orientation` change) plus a "rotate your phone" hint (`.history-hint`).
  Native fullscreen exit (system gesture) also closes the overlay.

## The Cono view (elastic Y-axis)

A second toggle `[data-view-switch]` (buttons `[data-view="abs|cono"]`, same
styling as the X-mode switch, state var `view`, default `abs`) flips between
the **absolute** axis (fixed 0→`maxVal`) and the **cono** (funnel/megaphone)
view. The cono is a **pure render transform** on the same embedded data — no
backend, no template-data change. It all lives in `render()` in `progress.js`.

**Why:** everyone advances roughly in parallel, so on the absolute axis the
lines pack into a thin diagonal band and early differences are invisible. The
cono trades *absolute-points readability* for *relative-position readability*:
the axis follows the cloud so player gaps stay legible from start to end.

**How (the `if (view === "cono")` block builds `bands`):**
1. Per column, take min/max of **all** players → the cloud's lower/upper
   envelope. All players, not the selection, so the axis does **not** jump when
   you select/deselect — selection only changes which lines are highlighted.
2. Fit **two straight lines** to those envelopes by least squares (`fitLine`),
   **excluding the origin column** (everyone at 0) so the fit isn't pinched to
   0 on the left.
3. **Shift each line outward** by its max deviation (`dDown`/`dUp`) so the band
   *contains* the cloud — the lines no longer pass through 0, and an early
   tanker stays inside the cone instead of hitting the floor. Plus a tiny
   `0.02` cushion.
4. Map each column's data range `[dlo, dhi]` into a pixel band whose height
   grows **45%→100%** left→right (`pxH = (0.45 + 0.55·xf)·plotH`), vertically
   centered — the megaphone. `xf` is the **weighted** horizontal position
   (cumulative weight = matches × `multiplier`, same as the X-axis), not the
   date or column index.
5. `Y(val, i) = botPx[i] - (val - dlo[i]) / dataH[i] · pxH[i]`. Only the column
   vertices are remapped (straight segments between), so the scale changes
   continuously and a constant-rate scorer renders as a **smooth curve**, not a
   straight line — by design, confirmed acceptable.

Net effect: **px-per-point shrinks left→right** (more zoom early, where the
real spread is tiny), so early differences become visible while the late spread
still fits.

**Cono chrome** (only in `view === "cono"`, drawn behind the data):
- Numeric Y grid is **skipped** (a constant value is no longer horizontal); the
  grey **curtain is kept** (it floats around the cone, clipped to the plot).
- **Anti-faro fill**: the cone trapezoid filled `#000` at low opacity to
  *darken* the area (not lighten it — lightening was a bug).
- **Frame**: the two envelope edges as straight `.hist-envelope` lines.
- **Iso-value curves**: constant-point reference lines at round steps
  (`niceStep`, ~`maxVal / 7`), dotted like the original grid, each labelled
  where it enters/exits the cone; the `0` line is dashed (`.hist-zero`).
- Critical SVG styling (`fill="none"`, strokes) is set **inline** as
  presentation attributes: without it an open `<path>` defaults to `fill:black`
  (the original "anti-faro" artifact) and lines vanish when `tailwind.css` is
  stale.

**Tunables** (literals in `render()`): cone start `0.45`, cushion `0.02`, fill
opacity, iso count `maxVal / 7`. **Pending:** iso-line label placement
(above/below the cone) still needs polish.

**Math test:** `.claude/historia_cone_math_test.mjs` — `node` it; replicates
`fitLine` + the band logic with synthetic data and asserts the invariants
(containment incl. an early tanker, 45→100% cone, px/point decreasing, steady
scorer curves). Re-run after touching the cono math.

## JS ↔ markup contract

These ids/classes are the wiring between the template, JS and CSS — renaming
any breaks the chart:

- `#history-chart` (SVG root), `#history-data` (`json_script` payload),
  `#history-users` (TomSelect `<select>`), `#history-legend`.
- `[data-xmode-switch]` wrapper and `[data-xmode="match|batch|day"]` buttons;
  active button gets `.active`. `[data-view-switch]` wrapper and
  `[data-view="abs|cono"]` buttons (same `.active` convention) flip the view.
- Runtime-toggled classes with real CSS: `.hist-line` + `.is-hi`/`.is-me`/
  `.is-hover`, `.hist-chip[data-me]`, `.history-xmode button.active`,
  `.history-chart.is-short` (thin lines). Cono chrome: `.hist-envelope` (frame)
  and `.hist-zero` (zero line) in `source.css`, but their critical styling is
  duplicated inline (see *The Cono view*).
- Immersive hooks: `[data-immersive-open]`/`[data-immersive-close]` buttons,
  `.history-back` (`chevron_left`, links to `{% url 'root' %}`), `.history-expand`,
  `.history-close`; body classes `history-immersive` + `is-rotated` drive the
  fullscreen-landscape CSS in `source.css`. New Material Symbols added to the
  `base.html` subset: `chevron_left`, `open_in_full`, `clear`.
- Palette/theme tokens live only in `source.css` (`--chart-*`); never hardcode
  colors in JS or the template.

## Dependencies & gotchas

- **Scores are frozen, never computed here.** The chart reads `ScoreSnapshot`
  rows produced by `evaluation.recompute_all` (runs on every result capture;
  `manage.py recompute_scores` backfills). If the chart looks stale or wrong
  after a result fix, the fix is to recompute snapshots, not to touch this code.
- **Every finished match has a snapshot per user** (even unpredicted, at the
  carried-forward cumulative), so there are no gaps — each tick has a value for
  every player.
- **Quiniela comes from the URL slug** (`request.quiniela` via `@with_quiniela`),
  and the cutoff + multipliers are per-quiniela. Test changes across
  `sanginiela`, `bienestar` (cutoff at Jornada 2) and `libres`.
- **Tailwind preflight forces `img { display:block }`**; flag `<image>` here is
  SVG so it's unaffected, but legend/markup flags elsewhere need `inline-block`.
- The venv is at `../sanginiela/venv` (see project memory). Quick check:
  `../sanginiela/venv/bin/python manage.py shell -c "from pool.services.progress
  import build_progress; ..."`.
