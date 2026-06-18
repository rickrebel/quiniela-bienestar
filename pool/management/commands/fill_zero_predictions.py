"""Crea predicciones 0-0 para los partidos de una fecha (todos los usuarios).

Para cada partido cuya fecha local sea ``--date`` (default 18/06/2026) y
cada usuario que aún no tenga predicción de ese partido, inserta una
predicción 0-0. Idempotente: respeta las predicciones ya existentes (la
restricción única es ``user`` + ``match``), así que volver a correrlo solo
rellena lo que falte.
"""

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from pool.models import Prediction, User
from tournament.models import Match

DATE_FORMAT = "%d/%m/%Y"
DEFAULT_DATE = "18/06/2026"


class Command(BaseCommand):
    help = (
        "Inserta predicciones 0-0 para todos los usuarios en cada partido "
        "de una fecha (default 18/06/2026), sin tocar las existentes."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--date", default=DEFAULT_DATE,
            help=f"Fecha de los partidos (DD/MM/AAAA). Default: "
                 f"{DEFAULT_DATE}.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo informa cuántas crearía, sin escribir en la BD.")

    def handle(self, *args, **options) -> None:
        target = self._parse_date(options["date"])

        # __date convierte a la zona horaria activa (igual que
        # timezone.localdate), así que filtra por la fecha local del partido.
        match_ids = list(
            Match.objects.filter(datetime__date=target)
            .values_list("id", flat=True)
        )
        if not match_ids:
            raise CommandError(
                f"No hay partidos el {options['date']}.")

        user_ids = list(User.objects.values_list("id", flat=True))
        existing = set(
            Prediction.objects.filter(match_id__in=match_ids)
            .values_list("user_id", "match_id")
        )

        now = timezone.now()
        to_create = [
            Prediction(
                user_id=user_id, match_id=match_id,
                home_goals=0, away_goals=0, date=now,
            )
            for user_id in user_ids
            for match_id in match_ids
            if (user_id, match_id) not in existing
        ]

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                f"[dry-run] Crearía {len(to_create)} predicción(es) 0-0 "
                f"para {len(match_ids)} partido(s) y {len(user_ids)} "
                f"usuario(s)."))
            return

        Prediction.objects.bulk_create(to_create)
        self.stdout.write(self.style.SUCCESS(
            f"Creadas {len(to_create)} predicción(es) 0-0 para "
            f"{len(match_ids)} partido(s) del {options['date']} y "
            f"{len(user_ids)} usuario(s)."))

    def _parse_date(self, value: str):
        try:
            return datetime.strptime(value, DATE_FORMAT).date()
        except ValueError:
            raise CommandError(
                f"Fecha inválida '{value}'; usa el formato DD/MM/AAAA.")