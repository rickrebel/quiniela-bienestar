"""Crea/actualiza las ventanas de predicción (``Window``) de cada quiniela.

Las definiciones viven aquí (como ``load_rules``): correr de nuevo el
comando sincroniza el agrupamiento vía ``update_or_create`` sobre
``(quiniela, order)``, sin pisar el calendario/peso que el admin haya
ajustado (``opens_at``/``send_deadline``/``multiplier``/
``third_place_multiplier`` no van en ``defaults``).

Estructura única compartida = las 8 fases atómicas. La diferencia entre
quinielas es **cómo las agrupan**: la original concentra las 3 jornadas
de grupos en una sola ventana "Grupos"; bienestar las separa. En las
ventanas 1:1 (una sola fase) ``name``/``color``/calendario quedan vacíos
y ``Window.resolved_*`` cae al valor de la fase; la ventana multi-fase
("Grupos") fija su nombre y el admin pone sus fechas.

Requiere las quinielas ya creadas (``load_rules`` antes).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from pool.models import Quiniela, Window
from tournament.models import Stage

# slug -> lista de ventanas. Cada ventana: order, stages (claves de fase)
# y, solo en la multi-fase, name/short_name explícitos.
WINDOWS = {
    "sanginiela": [
        {"order": 1, "name": "Grupos", "short_name": "Grupos",
         "stages": ["SUBGROUP_1", "SUBGROUP_2", "SUBGROUP_3"]},
        {"order": 2, "stages": ["LAST_32"]},
        {"order": 3, "stages": ["LAST_16"]},
        {"order": 4, "stages": ["QUARTER_FINALS"]},
        {"order": 5, "stages": ["SEMI_FINALS"]},
        {"order": 6, "stages": ["FINAL"]},
    ],
    "bienestar": [
        {"order": 1, "stages": ["SUBGROUP_1"]},
        {"order": 2, "stages": ["SUBGROUP_2"]},
        {"order": 3, "stages": ["SUBGROUP_3"]},
        {"order": 4, "stages": ["LAST_32"]},
        {"order": 5, "stages": ["LAST_16"]},
        {"order": 6, "stages": ["QUARTER_FINALS"]},
        {"order": 7, "stages": ["SEMI_FINALS"]},
        {"order": 8, "stages": ["FINAL"]},
    ],
}


class Command(BaseCommand):
    help = "Crea o actualiza las ventanas de predicción de cada quiniela."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        stages = {s.key: s for s in Stage.objects.all()}
        created = updated = 0

        for slug, windows in WINDOWS.items():
            quiniela = Quiniela.objects.filter(slug=slug).first()
            if quiniela is None:
                self.stderr.write(self.style.WARNING(
                    f"Quiniela '{slug}' no existe; corre load_rules. "
                    f"Se omite."))
                continue
            for spec in windows:
                window, was_created = Window.objects.update_or_create(
                    quiniela=quiniela,
                    order=spec["order"],
                    defaults={
                        "name": spec.get("name", ""),
                        "short_name": spec.get("short_name", ""),
                        "color": spec.get("color", ""),
                    },
                )
                window.stages.set([stages[k] for k in spec["stages"]])
                created += was_created
                updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f"Ventanas: {created} creadas, {updated} actualizadas."))
