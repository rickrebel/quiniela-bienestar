"""Descarga partidos reales terminados para alimentar ``simulate``.

Genera ``db/jsons/sim/cl2025.json`` con los FINISHED de la Champions
2025-26 (la temporada actual es lo único accesible en el tier gratuito;
las históricas, p. ej. Qatar 2022, son de pago). El archivo se commitea
y ``simulate`` lo lee offline — este comando se corre una vez (o con
``--force`` para regenerarlo).

El endpoint de lista ya incluye el score desglosado (``regularTime``,
``extraTime``, ``penalties``) en partidos terminados, así que no hacen
falta los details (que en CL además no traen ``goals[]``/``bookings[]``).
"""

import json
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

OUTPUT_PATH = Path("db/jsons/sim/cl2025.json")
COMPETITION = "CL"


class Command(BaseCommand):
    help = (
        "Descarga los partidos FINISHED de la Champions actual a "
        "db/jsons/sim/cl2025.json (fetch único; el archivo se commitea)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force", action="store_true",
            help="Regenera aunque el archivo ya exista.")

    def handle(self, *args, **options) -> None:
        if OUTPUT_PATH.exists() and not options["force"]:
            msg = f"{OUTPUT_PATH} ya existe; usa --force para regenerarlo."
            raise CommandError(msg)
        token = settings.FOOTBALL_DATA_API_TOKEN
        if not token:
            raise CommandError("Falta FOOTBALL_DATA_API_TOKEN en el .env.")

        url = (
            f"{settings.FOOTBALL_DATA_BASE_URL}/competitions/{COMPETITION}"
            "/matches?status=FINISHED"
        )
        response = requests.get(
            url, headers={"X-Auth-Token": token}, timeout=30)
        if response.status_code != 200:
            raise CommandError(
                f"FD respondió {response.status_code}: "
                f"{response.text[:200]}")
        data = response.json()
        matches = data["matches"]
        self._validate(matches)

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "competition": COMPETITION,
            "season": data.get("filters", {}).get("season"),
            "matches": matches,
        }
        with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {len(matches)} partidos en {OUTPUT_PATH}."))

    def _validate(self, matches: list[dict]) -> None:
        """Aborta si la API devolvió snapshots corruptos.

        Pasó en vivo: un FINISHED con ``winner: null`` y la tanda
        congelada a media serie (3-3), inconsistente con ``fullTime``.
        Mejor no escribir el archivo que commitear basura.
        """
        bad = []
        for m in matches:
            s = m["score"]
            if s.get("winner") is None:
                bad.append((m["id"], "winner null"))
                continue
            regular = s.get("regularTime")
            if regular is None:
                continue
            extra = s.get("extraTime") or {"home": 0, "away": 0}
            pens = s.get("penalties") or {"home": 0, "away": 0}
            for side in ("home", "away"):
                total = regular[side] + extra[side] + pens[side]
                if total != s["fullTime"][side]:
                    bad.append((m["id"], f"fullTime {side} inconsistente"))
                    break
        if bad:
            raise CommandError(f"Payloads corruptos de FD: {bad}")
