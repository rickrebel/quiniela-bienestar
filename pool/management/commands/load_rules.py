"""Crea/actualiza el catálogo de reglas de puntuación y las quinielas.

Las definiciones viven aquí: correr de nuevo el comando
sincroniza nombres, íconos y puntajes vía ``update_or_create``, así que
un cambio de definición se hace en el código y se reaplica, nunca a mano
en la base.

La regla PENALTY existe en el catálogo pero solo se enlaza a la quiniela
``bienestar``: es justo lo que diferencia ambas quinielas. La default
(la que usa hoy el scoring) no se pisa si ya está fijada: el admin elige.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from pool.models import Quiniela, QuinielaRule, Rule

# Catálogo global: definición y presentación, sin puntaje.
RULE_CATALOG = [
    {
        "code": "RESULT",
        "name": "Resultado",
        "short_name": "Res",
        "icon": "check",
        "description": "Atinaste al ganador o al empate.",
        "order": 1,
    },
    {
        "code": "DIFF",
        "name": "Diferencia",
        "short_name": "Dif",
        "icon": "",
        "description": "Atinaste la diferencia de goles "
                       "(no aplica en empates).",
        "order": 2,
    },
    {
        "code": "EXACT",
        "name": "Marcador exacto",
        "short_name": "Exacto",
        "icon": "mira",
        "description": "Atinaste el marcador exacto.",
        "order": 3,
    },
    {
        "code": "PENALTY",
        "name": "Penales",
        "short_name": "Pen",
        "icon": "sports_soccer",
        "description": "Atinaste quién gana la tanda de penales y avanza.",
        "order": 4,
    },
]

# Puntaje base por quiniela. La original no puntúa penales.
QUINIELAS = [
    {
        "slug": "sanginiela",
        "name": "Sanginiela",
        "theme": "sanginiela",
        "rules": {"RESULT": 3, "DIFF": 1, "EXACT": 1},
    },
    {
        "slug": "bienestar",
        "name": "Quiniela del bienestar",
        "theme": "bienestar",
        "rules": {"RESULT": 3, "DIFF": 1, "EXACT": 1, "PENALTY": 1},
    },
]


class Command(BaseCommand):
    help = "Sincroniza el catálogo de reglas y las quinielas con su puntaje."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        for spec in RULE_CATALOG:
            code = spec.pop("code")
            Rule.objects.update_or_create(code=code, defaults=spec)
            spec["code"] = code  # restaura por si el comando se reusa
        rules_by_code = {r.code: r for r in Rule.objects.all()}

        for spec in QUINIELAS:
            quiniela, _ = Quiniela.objects.update_or_create(
                slug=spec["slug"],
                defaults={"name": spec["name"], "theme": spec["theme"]})
            for code, points in spec["rules"].items():
                QuinielaRule.objects.update_or_create(
                    quiniela=quiniela, rule=rules_by_code[code],
                    defaults={"points": points})

        self.stdout.write(self.style.SUCCESS(
            f"{Rule.objects.count()} reglas, "
            f"{Quiniela.objects.count()} quinielas."))