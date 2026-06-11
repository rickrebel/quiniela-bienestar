"""Carga resultados FINALES simulados de partidos (solo en local).

Pensado para experimentar la visualización de marcadores y comparar las
predicciones contra resultados reales sin depender de football-data. Llena
lo mínimo en ``Match``: marcador, tarjetas, ``decided_by=REGULAR`` (fase de
grupos) y ``status=FINISHED``. No toca penales.

Edita el dict ``SIMULATED`` para probar otros marcadores. ``--reset`` deja
esos partidos otra vez en blanco (``TIMED``) para volver a iterar.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tournament.models import Match


# Marcadores simulados — EDITA LIBREMENTE. Clave = ``of_number`` del partido.
# Por defecto: los 4 primeros del grupo A por fecha (jornadas 1 y 2).
SIMULATED = {
    1: {"label": "MEX vs RSA", "home_goals": 2, "away_goals": 1,
        "home_yellow": 2, "away_yellow": 3, "home_red": 0, "away_red": 0},
    2: {"label": "KOR vs CZE", "home_goals": 1, "away_goals": 1,
        "home_yellow": 1, "away_yellow": 2, "home_red": 0, "away_red": 1},
    25: {"label": "CZE vs RSA", "home_goals": 0, "away_goals": 2,
         "home_yellow": 3, "away_yellow": 1, "home_red": 0, "away_red": 0},
    28: {"label": "MEX vs KOR", "home_goals": 1, "away_goals": 0,
         "home_yellow": 2, "away_yellow": 2, "home_red": 1, "away_red": 0},
}

SCORE_FIELDS = (
    "home_goals", "away_goals",
    "home_yellow", "away_yellow", "home_red", "away_red",
)


class Command(BaseCommand):
    help = "Carga resultados finales simulados (solo en local)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset", action="store_true",
            help="Borra los resultados simulados y vuelve a TIMED.")
        parser.add_argument(
            "--force", action="store_true",
            help="Permite correr aunque la BD no sea SQLite.")

    def handle(self, *args, **options) -> None:
        self._guard_local(options["force"])
        if options["reset"]:
            self._reset()
        else:
            self._load()

    def _guard_local(self, force: bool) -> None:
        """Bloquea el comando fuera de local (``DEBUG`` es el proxy).

        Producción fija ``DEBUG=False``; en local es ``True``. El motor de
        BD no sirve de proxy porque en local también se usa Postgres.
        """
        if not settings.DEBUG and not force:
            msg = (
                "DEBUG=False (parece producción). Comando solo para local; "
                "usa --force si de verdad lo quieres."
            )
            raise CommandError(msg)

    def _load(self) -> None:
        matches = {
            m.of_number: m
            for m in Match.objects.filter(of_number__in=SIMULATED)
        }
        missing = set(SIMULATED) - set(matches)
        if missing:
            raise CommandError(
                "Faltan partidos sembrados: %s" % sorted(missing))
        for of_number, data in SIMULATED.items():
            match = matches[of_number]
            for field in SCORE_FIELDS:
                setattr(match, field, data[field])
            match.decided_by = Match.REGULAR
            match.status = "FINISHED"
            match.save()
            self.stdout.write(self.style.SUCCESS(
                "  #%d %s -> %d-%d" % (
                    of_number, data["label"],
                    data["home_goals"], data["away_goals"])))
        self.stdout.write(self.style.SUCCESS(
            "Listo: %d partidos finalizados." % len(SIMULATED)))

    def _reset(self) -> None:
        qs = Match.objects.filter(of_number__in=SIMULATED)
        count = qs.update(
            home_goals=None, away_goals=None,
            home_yellow=None, away_yellow=None,
            home_red=None, away_red=None,
            decided_by="", status="TIMED")
        self.stdout.write(self.style.WARNING(
            "Reset: %d partidos vueltos a TIMED, sin marcador." % count))