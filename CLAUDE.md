# sanginiela

Family World Cup pool. Pre-registered players log in with just their email
(no password), predict group-stage scores, and on submit receive an Excel of
their picks by email. Django server-rendered (no DRF), DTL templates + vanilla
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
  save/send/confirm).
- Excel generation + email in `pool/services/excel.py`.
- Data seeded from two sources committed under `db/jsons/`: OF (openfootball,
  base seed) and FD (football-data.org, `fd_id` + results). Manual overrides
  (e.g. Spanish names) in `db/jsons/manual/`; old files in `db/jsons/legacy/`.

## Gotchas

- **No passwords.** Login is email-only (`views/auth.py`); `is_active=False`
  means pre-registered but not yet entered. The custom `UserManager` calls
  `set_unusable_password()`.
- **`username` always equals `email`** (forced in `User.save()`). The player's
  display name lives in `first_name`, not `username`.
- **`home`/`away`, not `a`/`b`.** Models, templates and `static/submit.js` all
  use `home_team`/`away_team`, `home_goals`/`away_goals`, aligned with FD.
- **Per-stage flow.** Predictions are scoped to a `Stage` (tabs at
  `/stage/<key>/`). `StageUser.state` is a computed lifecycle
  (`upcoming`→`editing`→`sent`→`confirmed`, plus `locked`) derived from
  `sent_at`, `closed_at`, `Stage.opens_at` and `Stage.confirm_deadline`. A
  stage is editable only once `opens_at` is set and reached (null = not yet
  enabled). `close_expired_stages` (cron, pending on EC2) auto-confirms sent
  stages past their deadline.
- **`Match.datetime` is UTC**; local stadium time derives from
  `Stadium.utc_offset` (int). Group/`Stage` is derived on Match, not stored;
  `group_name` lives only on `Team` (CHOICES A–L).
- **OF↔FD team join is by code** (`fifa_code` == `tla`), with one override
  `URU`→`URY` (Uruguay). Match join is by (UTC datetime + home `tla`).
- **`Stage` has 6 rows, not 7**: FD `THIRD_PLACE`+`FINAL` collapse into `FINAL`;
  distinguish via `Match.of_number` (103 = third place, 104 = final). Note the
  ES false friend: `LAST_32` = "dieciseisavos", `LAST_16` = "octavos".
- **`send`/`confirm` persist first, then build the Excel**, so the file
  reflects what was sent. Keep that order.
- **JSON endpoints use a trailing slash** and require the `X-CSRFToken` header
  (set in `static/submit.js`).

## Deploy

Targets AWS (EC2 + RDS Postgres). Production reads `POSTGRES_*` from the
environment; local dev with no `POSTGRES_DB` uses SQLite. Run
`collectstatic` before serving in production.
