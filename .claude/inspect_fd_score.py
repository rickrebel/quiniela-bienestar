"""Puntual: compara el score del detail (raw_fd) vs el endpoint de lista."""
import json

import requests
from django.conf import settings

from tournament.models import Match


def run() -> None:
    match = Match.objects.get(of_number=1)
    print("--- detail (raw_fd) ---")
    print("status:", match.raw_fd.get("status"))
    print(json.dumps(match.raw_fd.get("score"), indent=2))

    url = f"{settings.FOOTBALL_DATA_BASE_URL}/competitions/WC/matches"
    headers = {"X-Auth-Token": settings.FOOTBALL_DATA_API_TOKEN}
    data = requests.get(url, headers=headers, timeout=30).json()
    listed = next(
        (m for m in data.get("matches", []) if m["id"] == match.fd_id),
        None,
    )
    print("--- lista ---")
    if listed is None:
        print("No apareció en la lista:", list(data.keys()))
    else:
        print("status:", listed.get("status"))
        print(json.dumps(listed.get("score"), indent=2))


run()
