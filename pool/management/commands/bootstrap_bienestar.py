"""Bootstrap del fork "bienestar" sobre un clon de la BD original.

Flujo completo (ver README): clonar la BD original con ``pg_dump | psql``,
aplicar migraciones y correr este comando. Es idempotente y reentrante.

Transforma la única fase ``GROUP_STAGE`` del original en 3 sub-fases de
grupos (``SUBGROUP_1/2/3``) reasignando SOLO el FK ``stage`` de cada
partido de grupo (no toca marcadores ni ``status``: los resultados reales
clonados se conservan). Después reinicia el estado de la quiniela:

- borra las predicciones de la 1.ª jornada (ya jugada; ``SUBGROUP_1`` nace
  cerrada con ``send_deadline`` en el pasado),
- pone todos los ``sent_at`` de ``StageUser`` en null (nada congelado),
- recrea los ``StageUser`` de las nuevas sub-fases (``sync_stageusers``).

``SUBGROUP_2/3`` quedan con fechas a null: el admin fija ``opens_at`` y
``send_deadline`` en el panel, como el resto de fases.
"""

from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from pool.models import Prediction, StageUser
from tournament.models import Match, Stage
from tournament.services.group_rounds import (
    SUBGROUP_COLOR,
    SUBGROUP_STAGES,
    round_by_match,
)

GROUP_STAGE_KEY = "GROUP_STAGE"
# Las 5 eliminatorias quedan en orders 4..8, tras las 3 sub-fases.
KNOCKOUT_KEYS = [
    Stage.LAST_32,
    Stage.LAST_16,
    Stage.QUARTER_FINALS,
    Stage.SEMI_FINALS,
    Stage.FINAL,
]


class Command(BaseCommand):
    help = (
        "Convierte un clon de la BD original en la quiniela bienestar: "
        "parte grupos en 3 sub-fases, borra predicciones de la jornada 1 "
        "y reinicia los envíos. Idempotente."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirma la operación (borra predicciones y envíos).",
        )

    def handle(self, *args, **options) -> None:
        if not options["yes"]:
            raise CommandError(
                "Operación destructiva (borra predicciones de la jornada "
                "1 y reinicia envíos). Reejecuta con --yes."
            )

        with transaction.atomic():
            substages = self._ensure_substages()
            reassigned = self._reassign_group_matches(substages)
            self._drop_old_group_stage()
            self._normalize_orders(substages)
            self._close_round_one(substages)
            deleted = self._purge_round_one_predictions()
            reset = StageUser.objects.update(sent_at=None)

        call_command("sync_stageusers")

        self.stdout.write(self.style.SUCCESS(
            f"Bienestar listo: {len(substages)} sub-fases de grupos, "
            f"{reassigned} partidos reasignados, "
            f"{deleted} predicciones de jornada 1 borradas, "
            f"{reset} StageUser con sent_at reiniciado."
        ))

    def _ensure_substages(self) -> list[Stage]:
        """Crea/actualiza ``SUBGROUP_1/2/3`` con orders temporales (900+).

        El order definitivo se asigna en ``_normalize_orders`` para no
        chocar con la unicidad mientras coexisten con ``GROUP_STAGE`` y las
        eliminatorias. No toca ``opens_at``/``send_deadline`` (preserva lo
        que el admin haya fijado en una reejecución).
        """
        substages = []
        for offset, (key, name, short, _order) in enumerate(SUBGROUP_STAGES):
            stage, _ = Stage.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "short_name": short,
                    "color": SUBGROUP_COLOR,
                    "is_group": True,
                    "order": 900 + offset,
                },
            )
            substages.append(stage)
        return substages

    def _reassign_group_matches(self, substages: list[Stage]) -> int:
        """Mueve cada partido de grupo a su sub-fase por ronda derivada.

        Toma los partidos que cuelgan de la vieja ``GROUP_STAGE`` (primer
        corrida) o ya de una sub-fase (reejecución). Solo escribe el FK
        ``stage``; los marcadores y el ``status`` quedan intactos.
        """
        sub_by_round = {i + 1: s for i, s in enumerate(substages)}
        matches = list(
            Match.objects.filter(
                Q(stage__key=GROUP_STAGE_KEY) | Q(stage__is_group=True)
            ).select_related("home_team", "stage")
        )
        rounds = round_by_match(matches)

        count = 0
        for match in matches:
            target = sub_by_round[rounds[match.id]]
            if match.stage_id != target.id:
                match.stage = target
                match.save(update_fields=["stage"])
                count += 1
        return count

    def _drop_old_group_stage(self) -> None:
        """Elimina la fase ``GROUP_STAGE`` huérfana (ya sin partidos).

        ``StageUser.stage`` es ``PROTECT``; se borran sus filas vía la
        relación inversa antes de eliminar la fase (se recrean luego con
        ``sync_stageusers``).
        """
        old = Stage.objects.filter(key=GROUP_STAGE_KEY).first()
        if old is None:
            return
        if old.matches.exists():
            raise CommandError(
                "GROUP_STAGE aún tiene partidos: reasignación incompleta."
            )
        old.user_states.all().delete()
        old.delete()

    def _normalize_orders(self, substages: list[Stage]) -> None:
        """Fija los orders definitivos 1..8 (3 sub-fases + 5 eliminatorias).

        Dos pasadas para no violar la unicidad: primero a temporales 1000+
        (libera el rango 1..8), luego a los definitivos. De paso confirma
        ``is_group`` (True en sub-fases, False en eliminatorias).
        """
        knockout = list(
            Stage.objects.filter(key__in=KNOCKOUT_KEYS).order_by("order")
        )
        ordered = list(substages) + knockout
        for temp, stage in enumerate(ordered, start=1000):
            Stage.objects.filter(pk=stage.pk).update(order=temp)
        for final, stage in enumerate(ordered, start=1):
            Stage.objects.filter(pk=stage.pk).update(
                order=final, is_group=stage in substages
            )

    def _close_round_one(self, substages: list[Stage]) -> None:
        """Deja ``SUBGROUP_1`` cerrada: deadline = primer partido (pasado).

        ``opens_at`` un día antes para que el estado derive a LOCKED. Las
        otras dos sub-fases conservan sus fechas (null = las pone el admin).
        """
        sub1 = substages[0]
        first = sub1.matches.order_by("datetime").first()
        if first is None:
            return
        sub1.opens_at = first.datetime - timedelta(days=1)
        sub1.send_deadline = first.datetime
        sub1.save(update_fields=["opens_at", "send_deadline"])

    def _purge_round_one_predictions(self) -> int:
        """Borra las predicciones de la 1.ª jornada (ya jugada)."""
        deleted, _ = Prediction.objects.filter(
            match__stage__key="SUBGROUP_1"
        ).delete()
        return deleted
