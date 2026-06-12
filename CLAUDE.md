# sanginiela

Family World Cup pool. Pre-registered players log in with their email and a
password they set on first access, predict group-stage scores, and on submit
receive an Excel of their picks by email. Django server-rendered (no DRF), DTL templates + vanilla
JS. See `README.md` for full setup.

## Commands

The project venv lives at `D:\env\quiniela` (interpreter:
`D:\env\quiniela\Scripts\python.exe`).

- `python manage.py runserver` — local dev server (http://localhost:8000/)
- `python manage.py check` — validate models/URLs/imports without a DB
- Seed (in order; each depends on the prior — `tournament` app):
  `load_stadiums` → `load_stages` → `load_teams` → `load_matches`,
  reading from `db/jsons/{of,fd,manual}/`.
- `python manage.py preregister <email> "<name>"` — add a player (`pool` app)
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
  `StageUser`.
- Views split by concern in `pool/views/`: `auth.py` (email login),
  `stages.py` (per-stage predictions page + tabs), `predictions.py` (JSON
  save + per-match autosave + send).
- Excel generation + email in `pool/services/excel.py`.
- Data seeded from two sources committed under `db/jsons/`: OF (openfootball,
  base seed) and FD (football-data.org, `fd_id` + results). Manual overrides
  (e.g. Spanish names) in `db/jsons/manual/`; old files in `db/jsons/legacy/`.

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
- **`Stage` has 6 rows, not 7**: FD `THIRD_PLACE`+`FINAL` collapse into `FINAL`;
  distinguish via `Match.of_number` (103 = third place, 104 = final). Note the
  ES false friend: `LAST_32` = "dieciseisavos", `LAST_16` = "octavos". OF omits
  `num` for group matches **and** for third place/final, so group detection keys
  off the round (`Matchday*`), never `num` presence.
- **Per-match autosave.** Scores save on `change` via `save_prediction`
  (`/prediction/<id>/`), not a bulk submit. A `Prediction` row exists only when
  both goals are set — an incomplete match deletes its row. Completeness and
  the `N/total` counters derive from row presence, not form state.
- **`send` finalizes what's already in the DB**: it doesn't re-persist the
  client payload, just sets `sent_at`, then builds the Excel. Keep that order
  so the file matches what was sent.
- **JSON endpoints use a trailing slash** and require the `X-CSRFToken` header
  (set in `static/submit.js`).

## Deploy

Targets AWS (EC2 + RDS Postgres), nginx terminating TLS in front of gunicorn
(`SECURE_PROXY_SSL_HEADER` is set; prod also needs `CSRF_TRUSTED_ORIGINS` or
POSTs get 403). Env vars are parsed via `config/get_env.py`; production reads
`POSTGRES_*`, local dev with no `POSTGRES_DB` uses SQLite. Run `collectstatic`
before serving in production.
