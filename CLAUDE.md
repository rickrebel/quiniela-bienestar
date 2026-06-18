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
- `python manage.py preregister <email> "<name>"` — add a player (`pool` app)
- `python manage.py bootstrap_bienestar --yes` — one-time fork bootstrap over
  a **clone** of the original DB (`pool` app, idempotent): splits the group
  stage into `SUBGROUP_1/2/3` (reassigns only `Match.stage`, never results),
  deletes round-1 predictions, nulls every `StageUser.sent_at`. Clone the DB
  first with `pg_dump | psql` (see README); `POSTGRES_DB_ORIGINAL` names the
  source. `SUBGROUP_2/3` dates are set by hand in the admin afterwards.
- `python manage.py build_collective_profile <stage_key>` — freeze the
  virtual profile's aggregated predictions for a closed stage (`pool` app)
- `python manage.py fetch_sim_source` — one-time download of real finished
  matches (current Champions season; free FD tier has no historic seasons)
  to `db/jsons/sim/cl2025.json`, committed (`tournament` app).
- `python manage.py simulate [--day N]` — leave the local DB as if today were
  day N of the World Cup: shifts the calendar, applies real disguised results
  from `cl2025.json`, fills predictions and marks sends (`pool` app).
  Local-only: refuses to run with `DEBUG=False` unless `--force`. No reset:
  re-seed or restore a backup to undo.
- DB selection is env-driven: set `POSTGRES_DB` for Postgres, leave it empty
  to fall back to SQLite at `db/app.sqlite3`.

## Architecture

- Two apps; project package `config/`. Dependency is one-way: `pool` imports
  from `tournament`, never the reverse.
- `tournament/`: sports data models (`Stadium`, `Stage`, `Team`, `Match`).
- `pool/`: `User` (custom, `AUTH_USER_MODEL = "pool.User"`), `Prediction`,
  `StageUser`, `PasswordRecoveryToken`.
- Views split by concern in `pool/views/`: `auth.py` (login + password
  recovery), `stages.py` (per-stage predictions page + tabs + result cards),
  `predictions.py` (JSON save + per-match autosave + send), `leaderboard.py`
  (standings page).
- Business logic in `pool/services/`, one module per concern: excel,
  scoring, standings, leaderboard, aggregation, match_dialog, recovery.
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
- **Per-stage flow.** Predictions are scoped to a `Stage` (tabs at
  `/stage/<key>/`). Sending is single and final. `StageUser.state` is a
  computed lifecycle (`upcoming`→`editing`→`sent`, plus `locked`) derived from
  `sent_at`, `Stage.opens_at` and `Stage.send_deadline`. A stage is editable
  only once `opens_at` is set and reached (null = not yet enabled).
  `send_expired_stages` (cron, pending on EC2) auto-sends whatever was saved
  for stages past their deadline (skips users who saved nothing).
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
- **Group stage = 3 sub-stages, one UI tab.** `Stage.is_group=True` marks the
  3 matchday sub-stages; the UI **collapses them into a single "Grupos" tab**
  that shows all groups A-L. Use `stage.is_group` (never `key ==
  "GROUP_STAGE"`) and query group matches with `stage__is_group=True`. The
  group **standings table is cumulative** across the 3 sub-stages, but
  **editability and `send` are per sub-stage**: only the live matchday is
  editable, and "Enviar" finalizes just that sub-stage's `StageUser`.
  `SUBGROUP_1` is born closed (matchday 1 already played).
- **`Stage.multiplier`** (Decimal, default 1) is a per-stage scoring weight
  (1, 1.5, 2 … 10×) stored in the DB but **NOT yet applied** by
  `scoring.py` — pending.
- **`Prediction.advancing_team`** (FK→Team, nullable) records who the player
  thinks wins the penalty shootout when they predict a knockout draw. Stored
  but with **no frontend nor scoring logic yet** — pending.
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
- **Virtual profile** ("Ignorancia colectiva", `User.is_virtual`): shows in
  standings, can't log in, out of prizes, excluded from
  `send_expired_stages`. `build_collective_profile` only runs after the
  stage's `send_deadline` — aggregating earlier would leak the crowd's pick.
- **Password recovery uses its own `PasswordRecoveryToken`** (UUID PK, 24 h,
  single-use), not Django's token generator. When building the email link,
  `SITE_URL` overrides `request.build_absolute_uri` (needed behind ngrok).
- **Real results sync is NOT implemented yet** (`sync_results` pending; see
  the `football-data-matches` skill). A match renders as "live" via a 2-hour
  window in `views/stages.py`, not real-time data. The `standing` context
  processor runs on every template and must degrade to `{}` on any error.
- **JS↔markup contract.** Several classes are pure JS hooks (no CSS of their
  own anymore): `.content[data-stage|state]`, `.group`/`.knockout`,
  `.group-summary`, `.chip-title`, `.chevron`, `.group-flags`,
  `.section-count`, `.match-card`, `.match[data-match-id]`,
  `[data-field=*_goals]`, `.score`, `.team`, `.team-placeholder`, `.meta`,
  `.deadline-note`. Renaming them in templates breaks `submit.js`,
  `standings.js`, `match_dialog.js` or `countdown.js`. `pick-win`/`pick-tie`,
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
