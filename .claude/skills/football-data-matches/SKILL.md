---
name: football-data-matches
description: >
  Fetch and sync World Cup match results from the football-data.org API (v4)
  into the tournament.Match model. Use whenever syncing results, scores,
  cards, or penalties; pulling fixtures; calling football-data / FD; or
  working with the X-Auth-Token API. Base data (teams, stadiums, fixtures)
  is already seeded — this skill is for live match results over time.
---

# football-data-matches

How to read match data from **football-data.org v4** and map it onto the
`tournament.Match` model. Base seeding (teams, stadiums, fixtures, `fd_id`)
is already done by the `load_*` commands; this skill covers the recurring
**results sync**.

## Auth & config

Token lives in `.env` as `FOOTBALL_DATA_API_TOKEN`, exposed in settings:

```python
from django.conf import settings
settings.FOOTBALL_DATA_API_TOKEN   # personal token
settings.FOOTBALL_DATA_BASE_URL    # "https://api.football-data.org/v4"
```

Send it as the **`X-Auth-Token`** header (not a query param, not Bearer):

```python
import requests
from django.conf import settings

headers = {"X-Auth-Token": settings.FOOTBALL_DATA_API_TOKEN}
url = f"{settings.FOOTBALL_DATA_BASE_URL}/competitions/WC/matches"
data = requests.get(url, headers=headers, timeout=30).json()
```

**Rate limit:** free tier ≈ 10 requests/minute. The WC competition is
included in the free tier. Throttle batches (e.g. `time.sleep(6)` between
detail calls) and only fetch detail for matches that just finished.

## Two endpoints

| Endpoint | Use | Has cards/penalties? |
|---|---|---|
| `GET /competitions/WC/matches` | List all 104 matches (scores, status, group, stage) | **No** |
| `GET /matches/{id}` | Single match detail | **Yes** (`bookings`, `penalties`) |

The **list** endpoint is enough for scores + status. To fill cards and the
penalty shootout you must hit the **detail** endpoint per match.

## List response shape

```jsonc
{
  "matches": [{
    "id": 537327,                       // -> Match.fd_id (already seeded)
    "utcDate": "2026-06-11T19:00:00Z",
    "status": "TIMED",                  // -> Match.status
    "stage": "GROUP_STAGE",
    "group": "GROUP_A",
    "homeTeam": {"id": 769, "tla": "MEX", "name": "Mexico"},
    "awayTeam": {"id": 773, "tla": "RSA", "name": "South Africa"},
    "score": {
      "winner": null,                   // HOME_TEAM | AWAY_TEAM | DRAW
      "duration": "REGULAR",            // -> Match.decided_by
      "fullTime": {"home": null, "away": null},  // -> home_goals/away_goals
      "halfTime": {"home": null, "away": null}
    }
  }]
}
```

`status` values: `SCHEDULED, TIMED, IN_PLAY, PAUSED, FINISHED, SUSPENDED,
POSTPONED, CANCELLED, AWARDED`. Only `FINISHED` matches have a final score.

## Mapping FD → tournament.Match

Each `Match` row already carries `fd_id`, so **sync by `fd_id`** — no
re-matching by date/team is needed.

| FD field | Match field |
|---|---|
| `id` | `fd_id` (key, already set) |
| `status` | `status` |
| `score.fullTime.home` / `.away` | `home_goals` / `away_goals` |
| `score.duration` | `decided_by` (`REGULAR`/`EXTRA_TIME`/`PENALTY_SHOOTOUT`) |
| `bookings[]` (detail) | `home_yellow`/`away_yellow`/`home_red`/`away_red` |
| `penalties[]` (detail) | `home_penalties`/`away_penalties` |

`decided_by`, `home_penalties`, `away_penalties` and `is_final` /
`is_third_place` matter only in knockout. `score.fullTime` holds the score
at the end of regular/extra time; on a shootout (`duration ==
PENALTY_SHOOTOUT`) the shootout tally comes from `penalties[]`, not from
`fullTime`. ⚠️ The tournament hasn't started, so the exact `penalties[]`
shape for a finished match couldn't be verified live — confirm against a
real finished match before trusting the shootout count.

## Detail response (cards + penalties)

```jsonc
{
  "id": 537327,
  "homeTeam": {"id": 769, ...}, "awayTeam": {"id": 773, ...},
  "bookings":  [{"minute": 34, "team": {"id": 769}, "card": "YELLOW"}],
  "penalties": [{"player": {...}, "team": {"id": 769}, "scored": true}],
  "goals": [...], "referees": [...]
}
```

Resolve `team.id` against the match's `homeTeam.id` / `awayTeam.id` to bin
each booking/penalty into home vs away. Tally:

```python
def tally(detail):
    home_id = detail["homeTeam"]["id"]
    b = {"home_yellow": 0, "away_yellow": 0, "home_red": 0, "away_red": 0}
    for bk in detail.get("bookings", []):
        side = "home" if bk["team"]["id"] == home_id else "away"
        kind = "yellow" if bk["card"] == "YELLOW" else "red"
        b[f"{side}_{kind}"] += 1
    pens = detail.get("penalties", [])
    if pens:
        hp = sum(p["scored"] for p in pens if p["team"]["id"] == home_id)
        ap = sum(p["scored"] for p in pens if p["team"]["id"] != home_id)
        b["home_penalties"], b["away_penalties"] = hp, ap
    return b
```

## Sync sketch (future management command)

```python
# tournament/management/commands/sync_results.py (not yet implemented)
resp = requests.get(f"{base}/competitions/WC/matches", headers=headers)
by_fd = {m.fd_id: m for m in Match.objects.exclude(fd_id=None)}
for fm in resp.json()["matches"]:
    match = by_fd.get(fm["id"])
    if not match:
        continue
    ft = fm["score"]["fullTime"]
    match.status = fm["status"]
    match.home_goals, match.away_goals = ft["home"], ft["away"]
    match.decided_by = fm["score"]["duration"] or ""
    match.raw_fd = fm
    match.save()
    # then, only for FINISHED knockout matches, hit /matches/{id}
    # and apply tally() for cards + penalties (mind the rate limit).
```

Store the full FD payload in `Match.raw_fd` so future fields can be mined
without another request.
