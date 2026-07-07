---
name: mini-leaderboards
description: How the "Mini leaderboards" feature is built — the standings
  board filtered to a match subset (fase/fecha/equipo/grupo), its dialog and
  the inline filter row on /posiciones, the shared _filter_row.html, the
  filtered_board.js wiring and its TomSelect selects (equipo/grupo with
  flags). Use whenever working on the mini leaderboard / filtered board /
  sub-leaderboard, the /posiciones/filtrado/ endpoint, resolve_filter /
  filter_options, the [data-filtered-board] trigger buttons, or any TomSelect
  styling issue in the dialog (CDN cascade, daisyUI class leak).
---

# Mini leaderboards (filtered board)

A leaderboard restricted to a subset of matches, cut by **fase** (Stage),
**fecha** (local stadium date), **equipo** (Team) or **grupo** (letter).
It reuses `build_leaderboard(match_ids=...)` — same frozen points, no
trends — and renders in two contexts that share one filter row.

## File map

| File | Role |
|------|------|
| `pool/views/leaderboard.py` | `filtered_board_view`: GET-only, `?ambito=&valor=` (both empty = full board), `?part=board` returns only the table region. `leaderboard_view` adds `filter_options()` to /posiciones for the inline row. |
| `pool/services/leaderboard.py` | `resolve_filter(quiniela, ambito, valor)` → `(match_ids, label)`, raises `ValueError` → 400. `filter_options()` → selects data: `stages`, `groups` (letter + flags in real-table order via `_group_options`), `teams` (id/name/flag), `date_min/max/default`, `dates` (ISO days with matches, for prev/next). |
| `templates/_filter_row.html` | The shared filter row. `show_enable=True` (only /posiciones) renders the "Filtrar" checkbox; the dialog passes `False` (it always opens pre-filtered). |
| `templates/_filtered_board.html` | Dialog body: filter row + `[data-board-region]` + the three `json_script`s (`filtered-team-options`, `filtered-group-options`, `filtered-date-options`). |
| `templates/_filtered_board_region.html` | The swappable region: centered "Filtro: <label>" between `[data-filter-nav="prev|next"]` chevrons (only with a label) + `leaderboard_board.html with filtered=True` (no trends, no 🥖, no history link). |
| `templates/header.html` | The `<dialog id="filtered-board-dialog">` shell ("Mini leaderboards"). |
| `templates/leaderboard.html` | Inline context: `.filtered-board[data-inline-board]` wraps the row, `[data-board-full]` (the real board) and an empty `[data-board-region]`. |
| `static/filtered_board.js` | All wiring (see below). |
| `pool/urls.py` | `path("posiciones/filtrado/", ...)` under `/<slug>/`. |
| `pool/tests/test_filtered_leaderboard.py` | resolve_filter per ámbito, subset sums, view fragments, options shape, title chevrons. |

## Trigger buttons

Any element with `data-filtered-board data-ambito="..." data-valor="..."`
opens the dialog (delegated click in `filtered_board.js`). Current homes:
per-stage and per-date buttons in `por_fecha.html`, knockout header and
top-of-group button in `stage.html`, and the icon-only button in the
`team_dialog.html` head (its `data-valor` is set by `team_dialog.js` from
the fragment root's `data-team-id`).

## filtered_board.js essentials

- `wireFilterRow(root)` is **container-relative** (`.filtered-board`), never
  global IDs — /posiciones has the inline row *and* the dialog in the same
  document (duplicate `json_script` ids are tolerated because every lookup
  is `root.querySelector`).
- Region swaps fetch `?part=board` so the TomSelect instances survive.
  Inline, disabling the checkbox **hides/shows** `[data-board-full]` vs
  `[data-board-region]` instead of replacing HTML — leaderboard.js's trend
  switch keeps working because its nodes are never destroyed.
- `TS_KINDS` config-table maps a TomSelect ámbito (`equipo`, `grupo`) to
  its `json_script` id, value/label fields and option template (flags via
  `.ts-team-opt`). Adding another rich select = one more entry.
- TomSelect (CDN, same URLs as historia) loads lazily on first activation
  of a TS ámbito; after init, `sync()` must call `ts.enable()/disable()`
  (TomSelect ignores the underlying `disabled` attribute) and re-runs once
  the init resolves (guards the CDN-latency race).
- The `fecha` input always ships a value (`date_default` = today clamped
  to the tournament range) so the control is never blank.

## Prev/next navigation (title chevrons + swipe)

- The region title renders chevrons `[data-filter-nav="prev|next"]`
  around the centered "Filtro: X" **only when there is a filter label**.
  They step the *valor* of the active ámbito: fase by `<select>` DOM
  order, fecha over `dates` (`filtered-date-options` json_script — only
  days with matches), equipo/grupo over their json_scripts.
- Wiring lives in `wireFilterRow`: a **delegated** click on the root
  (the buttons are reborn on every region swap) calls `stepFilter(±1)`;
  `syncNav()` runs after every `refresh()` (and after TomSelect init)
  to disable the edge chevron — no wrap-around. TS values are set with
  `setValue(v, true)` (silent) and `refresh()` is called manually.
- Horizontal swipe (>48px, |dx|>|dy|) also steps, in **both contexts**
  (inline included — with the "Filtrar" checkbox off, `stepFilter`'s
  `enabled()` guard makes it inert). Passive listeners + dominant-axis
  check keep vertical scroll safe; gestures starting on
  `input/select/.ts-wrapper` are ignored.
- The match-detail dialog has the same pattern with its own endpoint
  (`/<slug>/partido/<id>/dialog/` → `stages.match_dialog_json`, payload +
  global chronological `prev_id`/`next_id`); see `match_dialog.js`
  (`navButton`/`fetchNav`/`navigate`) and `.dialog-nav` in `styles.css`.

## TomSelect styling gotchas (hard-won)

1. **Never put daisyUI classes on a TomSelect-ified `<select>`.** TomSelect
   copies the classList onto its `.ts-wrapper` div; daisyUI's `.select`
   brings `overflow:hidden` (clips the dropdown → "doesn't open"), a fixed
   height, arrow background-images and a `width: clamp(3rem,20rem,100%)`.
   The bare-select pattern is what makes historia's `#history-users` work.
2. **The CDN CSS loads after tailwind.css and wins ties.** Theme overrides
   live in `assets/css/source.css` prefixed with the container
   (`.filtered-board .ts-*`, shared selectors with `.history`). Three CDN
   rules needed extra specificity re-pisado: `.ts-wrapper.single
   .ts-control` (white gradient), `.single.input-active .ts-control`
   (white while focused/typing), and `.ts-control > *` (forces
   inline-block on the selected item, killing `.ts-team-opt`'s flex gap —
   in the dropdown the template is wrapped in `.option`, so only the
   control item needs the fix).
3. **No `dropdownParent: 'body'`**: outside the modal `<dialog>` the
   dropdown would be inert. Instead `.filtered-board .ts-dropdown-content`
   caps at 13rem to fit the scrollable `.send-dialog-body`.
4. After touching templates or `source.css`, run
   `manage.py tailwind build` — a stale dist silently drops the new
   utility classes (this bit us once).

## Server notes

- Filters cut **tournament** matches (global), then `build_leaderboard`
  intersects with FINISHED; `grupo` filters `stage__is_group=True` with
  `home_team__group_name` so knockout crossings between group mates don't
  count.
- `_group_options` starts from the `Team` catalog (not from matches, so no
  group disappears without fixtures) and orders each group's flags by the
  `real` variant of `standings.build_group_standings(matches, {})`.
- `filtered=True` in `leaderboard_board.html` suppresses trends, 🥖 and
  the history link, and switches the caption to "en este filtro".
