# sanginiela

Family World Cup pool. Pre-registered players log in with their email and a
password they set on first access, predict group-stage scores, and on submit
receive an Excel of their picks by email. As real results come in, the site
shows points per match, group standings and a leaderboard. Django
server-rendered (no DRF), DTL templates + vanilla JS. See `README.md` for
full setup.

## Commands

The project venv lives at `venv/` inside the repo (interpreter:
`venv/bin/python`).

- `python manage.py runserver` — local dev server (http://localhost:8000/)
- `python manage.py tailwind runserver` — dev server + Tailwind watcher;
  `tailwind build` recompiles once (needed before `collectstatic`).
- `python manage.py check` — validate models/URLs/imports without a DB
- `python manage.py test pool` — run the test suite (`pool/tests/`)
- Seed (in order; each depends on the prior — `tournament` app):
  `load_stadiums` → `load_stages` → `load_teams` → `load_matches`,
  reading from `db/jsons/{of,fd,manual}/`.
- `python manage.py load_rules` — seed/update the scoring-rule catalog and
  the quinielas with their base points (`pool` app, idempotent; definitions
  live in the command). Run once before `recompute_scores`.
- `python manage.py recompute_scores` — re-evaluate every prediction and
  rebuild the per-match cumulative snapshots (`pool` app; backfill or after a
  manual result fix). Capture already triggers this automatically.
- `python manage.py preregister <email> "<name>" <quiniela-slug>` — add a
  player and enroll them in a quiniela via `UserQuiniela` (`pool` app); the
  `UserQuiniela` signal materializes their `WindowUser`. Idempotent: an
  existing user can be enrolled in a further quiniela.
- `python manage.py build_collective_profile <window-order> --quiniela <slug>`
  — freeze the virtual profile's aggregated predictions for a closed
  **window** (all its stages; the "Grupos" window aggregates the 3 subgroups),
  scoped to one quiniela; freezes the virtual's `WindowUser` (`pool` app).
- `python manage.py extract_anexo_c` — regenerate the anexo C combinations
  JSON (`pool/services/data/anexo_c.json`) from `docs/anexo_c.html` with
  BeautifulSoup; idempotent, no DB (`pool` app).
- DB selection is env-driven: set `POSTGRES_DB` for Postgres, leave it empty
  to fall back to SQLite at `db/app.sqlite3`.

## Architecture

- Two apps; project package `config/`. Dependency is one-way: `pool` imports
  from `tournament`, never the reverse.
- `tournament/`: sports data models (`Stadium`, `Stage`, `Team`, `Match`).
- `pool/`: `User` (custom, `AUTH_USER_MODEL = "pool.User"`), `Prediction`,
  `Window`/`WindowUser`, `UserQuiniela`, `PasswordRecoveryToken`, scoring
  engine (`Quiniela`, `Rule`, `QuinielaRule`, `ScoreSnapshot`).
- Views split by concern in `pool/views/`: `auth.py` (login + password
  recovery), `stages.py` (per-stage predictions page + tabs + result cards),
  `predictions.py` (JSON save + per-match autosave + send), `leaderboard.py`
  (standings page).
- Business logic in `pool/services/`, one module per concern: excel,
  scoring, evaluation, standings, leaderboard, aggregation, match_dialog,
  recovery.
- Data seeded from two sources committed under `db/jsons/`: OF (openfootball,
  base seed) and FD (football-data.org, `fd_id` + results). Manual overrides
  (e.g. Spanish names) in `db/jsons/manual/`; old files in `db/jsons/legacy/`.
- **Frontend stack**: Tailwind v4 + daisyUI via `django-tailwind-cli`
  (standalone `tailwindcss-extra` binary, no Node; version pinned in
  settings). Source: `assets/css/source.css` (daisyUI theme + tokens;
  outside `static/` so collectstatic's Manifest storage never tries to
  resolve its `@import "tailwindcss"` as a file);
  dist `static/css/tailwind.css` is gitignored. Reusable template
  components are django-cotton (`templates/cotton/`, used as
  `<c-match-card :match="m" />`). Icons: Material Symbols subset via the
  Google Fonts `<link>` in `base.html` — adding an icon means adding its
  name to `icon_names` there.

## Gotchas

- **Password is set on first login, not at preregistration.** The custom
  `UserManager` creates players with `set_unusable_password()` and
  `is_active=False` (model default). On first login (`views/auth.py`) whatever
  password the user types becomes theirs and `is_active` flips to `True`;
  later logins verify it. So `is_active=False` = pre-registered, never
  entered.
- **`username` always equals `email`** (forced in `User.save()`). The player's
  display name lives in `first_name`, not `username`.
- **`home`/`away`, not `a`/`b`.** Models, templates and `static/submit.js` all
  use `home_team`/`away_team`, `home_goals`/`away_goals`, aligned with FD.
- **Per-window flow + quiniela by path (multi-quiniela).** The active quiniela
  comes from the URL prefix `/<slug>/…`: `config/urls.py` mounts `pool.urls`
  under `<slug:quiniela>/`, the `with_quiniela` decorator
  (`pool/views/scope.py`) sets `request.quiniela`, and `quiniela_for_host`
  auto-detects it from the domain (`QUINIELA_DOMAINS`). Auth is global
  (`pool/urls_auth.py`); old flat paths redirect via `legacy_redirect`.
  Predictions, sending and lifecycle scope to a **`Window`** (per-quiniela
  grouping of 1+ `Stage`), not a bare `Stage`: windows are the tabs at
  `/<slug>/ventana/<order>/` (`window_view`, one view for groups and
  knockouts). `WindowUser.state` (`upcoming`→`editing`→`sent`/`locked`) derives
  from `sent_at` and the window's `resolved_opens_at`/`resolved_send_deadline`
  (override, or fallback to its single stage). Sending is single/final **per
  window**; all cards in a window share its editable state.
  `send_expired_stages` auto-sends per window.
- **`Match.datetime` is UTC**; local stadium time derives from
  `Stadium.utc_offset` (int). Group/`Stage` is derived on Match, not stored;
  `group_name` lives only on `Team` (CHOICES A–L).
- **OF↔FD team join is by code** (`fifa_code` == `tla`), with one override
  `URU`→`URY` (Uruguay). Match join is by (UTC datetime + home `tla`).
- **`Stage` has 8 rows**: the group stage is split into 3 sub-stages
  (`SUBGROUP_1/2/3`, one per matchday, `is_group=True`, orders 1-3) plus the
  5 knockout stages (orders 4-8). FD `THIRD_PLACE`+`FINAL` collapse into
  `FINAL`; distinguish via `Match.of_number` (103 = third place, 104 = final).
  Note the ES false friend: `LAST_32` = "dieciseisavos", `LAST_16` =
  "octavos". OF omits `num` for group matches **and** for third place/final, so
  group detection keys off the round (`Matchday*`), never `num` presence.
  **Beware:** OF's `Matchday N` is the *global* calendar round (1–17), NOT each
  group's 1st/2nd/3rd game — the per-group round (→ `SUBGROUP_1/2/3`) is derived
  by sorting each group's 6 matches by `datetime` and chunking in pairs
  (`tournament/services/group_rounds.py:round_by_match`).
- **Group stage = 3 sub-stages, grouped by a `Window`.** `Stage.is_group=True`
  marks the 3 matchday sub-stages. `GROUP_STAGE` no longer exists (removed in
  1c): use `stage.is_group` and query group matches with
  `stage__is_group=True`, never a `key ==` check. The group **standings table
  is cumulative** across the 3 sub-stages. **Editability and `send` are per
  `Window`** (`WindowUser`), not per sub-stage: the original quiniela wraps
  all 3 sub-stages in one "Grupos" window (one tab showing groups A-L, sent as
  a unit); bienestar splits them into 3 separate 1:1 windows. `SUBGROUP_1` is
  born closed (matchday 1 already played).
- **Group tiebreaker = head-to-head FIRST** (FIFA 2026 rule change): teams
  level on points are ranked by the direct mini-league (h2h points, then h2h
  GD, GF) **before** overall GD/GF. Implemented in
  `standings.py:rank_group`/`_break_tie` (recursive mini-league), not by the
  scalar `StandingRow.sort_key` (that's only the global fallback when h2h
  doesn't separate). Final FIFA criterion (world ranking) is **not**
  implemented — residual ties keep a stable order.
- **Best 8 thirds + anexo C.** With 12 groups, the 8 best third-placed teams
  qualify; ranked by Pts, GD, GF, fair play (no h2h — different groups) in
  `pool/services/thirds.py:build_thirds`. Which third plays which group winner
  in LAST_32 comes from the **anexo C** combination table: static reference
  JSON `pool/services/data/anexo_c.json` (495 combos, **no DB**), regenerable
  from `docs/anexo_c.html` via `manage.py extract_anexo_c`. Lookup:
  `anexo_c.py:assign_thirds(qualified_groups)`; LAST_32 resolution +
  variant-aware thirds table wired in `views/stages.py:stage_view`.
- **`Window.multiplier`** (Decimal, default 1) is a per-window scoring weight
  (1, 1.5, 2 … 10×), resolved **per match** by
  `evaluation.py:multiplier_resolver` (the window of that quiniela whose
  `stages` contain `match.stage`). The nullable
  `Window.third_place_multiplier` overrides it for the third-place match
  only (`Match.is_third_place`, of_number 103) — same FINAL tab and send,
  different weight; null = inherit. Set via admin;
  `seed_windows` never writes either field.
  `evaluation.py` stores `Prediction.points = base × multiplier` (Decimal).
  Display as `{{ value|floatformat:"-1" }}` → "5" / "16.5".
- **`Prediction.advancing_team`** (FK→Team, nullable) records who the player
  thinks wins the penalty shootout when they predict a knockout draw, and
  **drives the `PENALTY` rule** (linked only to quinielas that use it, e.g.
  `bienestar`). Scoring lives in `evaluation.py:evaluate_scoreline`
  (`advancing_team_id` arg): `PENALTY` fires only when the quiniela has it
  **and** the match is knockout **and** `decided_by == PENALTY_SHOOTOUT` **and**
  the prediction is a draw **and** `advancing_team` == the shootout winner
  (`_penalty_winner_id`, more penalties). Capture UI: the two-button selector
  in `match_card.html` (`.advancing-pick`, shown by `submit.js` only on a
  predicted knockout draw); `save_prediction` persists it (and clears it when
  the score stops being a draw). The detail dialog **splits the draw subgroup
  per advancing pick** (`match_dialog.py:_split_by_advancing`) because the bonus
  is per-player, not per-scoreline. Chips: **`Dif` is omitted on any draw** and
  a **`Pen` chip** is shown on penalty knockouts (`scoring.py:chips_from_codes`,
  `show_penalty`). The sent Excel adds an **"Avanza" column** on knockout sheets
  (`excel.py:_advancing_cell`); the send-dialog summary collapses the selector
  to a read-only "Pasa: › 🏴 equipo" line (`submit.js:summarizeAdvancing`,
  `chevron_right` icon, already in the base.html subset).
- **Per-match autosave.** Scores save on `change` via `save_prediction`
  (`/prediction/<id>/`), not a bulk submit. A `Prediction` row exists only when
  both goals are set — an incomplete match deletes its row. Completeness and
  the `N/total` counters derive from row presence, not form state.
- **`send` finalizes what's already in the DB**: it doesn't re-persist the
  client payload, just sets `sent_at`, then builds the Excel. Keep that order
  so the file matches what was sent.
- **JSON endpoints use a trailing slash** and require the `X-CSRFToken` header
  (set in `static/submit.js`).
- **Scoring** (`pool/services/scoring.py`): 3 pts for the match result, +1
  for goal difference (never on draws), +1 for exact score (max 5, 4 on
  draws). Knockouts compare regular/extra-time goals, never penalties.
- **Scoring is frozen, not computed on the fly.** Each scoring rule is a
  `Rule` row (catalog: RESULT/DIFF/EXACT/PENALTY); `QuinielaRule` sets its
  base points **per `Quiniela`** (the original has no PENALTY). The active
  quiniela comes from the URL slug (`request.quiniela`), not a default flag;
  `recompute_all` iterates **every quiniela**, freezing scores independently.
  `evaluation.py:recompute_all`
  (idempotent, full rebuild) freezes `Prediction.points`/`base_points`/the
  `rules` M2M and rebuilds `ScoreSnapshot` (per user×match×quiniela cumulative
  for the progress charts; simultaneous matches share the tick's
  value/position). It
  runs on every result capture (`views/results.py`);
  `manage.py recompute_scores` backfills. `leaderboard.py` and the result
  cards/dialog **read these stored values** — they no longer call
  `score_detail` per page. `load_rules` seeds the catalog (idempotent
  `update_or_create`; definitions live in code).
- **Virtual profile** ("Ignorancia colectiva", `User.is_virtual`): shows in
  standings, can't log in, out of prizes, excluded from
  `send_expired_stages`. `build_collective_profile` only runs after the
  window's `resolved_send_deadline` — aggregating earlier would leak the
  crowd's pick.
- **Password recovery uses its own `PasswordRecoveryToken`** (UUID PK, 24 h,
  single-use), not Django's token generator. When building the email link,
  `SITE_URL` overrides `request.build_absolute_uri` (needed behind ngrok).
- **Results are captured manually, never synced.** The football-data API
  proved unreliable, so `sync_results` was dropped: trusted users
  (`can_record_results`) capture finished matches via `views/results.py`,
  which is also the only place that triggers `recompute_all`. A match renders
  as "live" via a 2-hour window in `views/stages.py`, not real-time data. The
  `standing` context processor runs on every template and must degrade to
  `{}` on any error.
- **JS↔markup contract.** Several classes are pure JS hooks (no CSS of their
  own anymore): `.content[data-window|state]`, `.group`/`.knockout`,
  `.group-summary`, `.chip-title`, `.chevron`, `.group-flags`,
  `.section-count`, `.match-card`, `.match[data-match-id]`,
  `[data-field=*_goals]`, `.score`, `.team`, `.team-placeholder`, `.meta`,
  `.deadline-note`, `.advancing-pick`/`.advancing-opt[data-advancing]`
  (selector de avance por penales). Renaming them in templates breaks
  `submit.js`, `standings.js`, `match_dialog.js` or `countdown.js`.
  `pick-win`/`pick-tie`, `.advancing-pick.show`/`.advancing-opt.is-picked`,
  `#snackbar .show`, `.view-opt.active` are toggled by JS at runtime, so
  they keep real CSS (styles.css or source.css), never inline utilities.
- **styles.css is legacy in retirement.** Unlayered CSS always beats
  Tailwind's layered utilities, so when migrating a view you must DELETE its
  old rules from `styles.css` or they silently override the new classes.
  What remains there: unmigrated views (board, rules), DOM that
  `match_dialog.js` builds (`day-*`, `pred-*`, `record-*`), the dialogs'
  shell (`send-dialog`), `.submit-btn` and `#snackbar`.
- **Don't name anything `.countdown`** (daisyUI component clashes; the
  deadline footer uses `.deadline-note`). Tailwind's preflight also makes
  every `img` display:block — inline flags need an explicit
  `inline-block` (see `.meta-flag`, `.pred-group-head img`).

## Deploy

Targets AWS (EC2 + RDS Postgres), nginx terminating TLS in front of gunicorn
(`SECURE_PROXY_SSL_HEADER` is set; prod also needs `CSRF_TRUSTED_ORIGINS` or
POSTs get 403, and `SITE_URL` so recovery emails link to the real domain).
Env vars are parsed via `config/get_env.py`; production reads `POSTGRES_*`,
local dev with no `POSTGRES_DB` uses SQLite. Run `manage.py tailwind build`
(the dist CSS is gitignored) and then `collectstatic` before serving in
production.
