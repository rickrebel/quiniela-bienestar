"""Clona los pronósticos de un usuario de una quiniela a otra.

Copia, de ``--source`` (por defecto sanginiela) a ``--target`` (por
defecto bienestar), todos los pronósticos crudos del usuario
(``home_goals``/``away_goals``/``advancing_team``) **excepto la JORNADA 1**
(``Stage.order == 1`` = ``SUBGROUP_1``). No copia los campos congelados
por la evaluación (``points``/``base_points``/``rules``): cada quiniela
tiene reglas y multiplicadores propios, así que los puntos se recongelan
con ``recompute_all`` al terminar.

Inscribe al usuario en la quiniela destino si no lo estaba (el signal de
``UserQuiniela`` materializa sus ``WindowUser``) y marca como enviadas
(``sent_at=ahora``) solo las ventanas destino que recibieron algún
pronóstico clonado, sin pisar un envío previo.

Idempotente: re-correrlo resincroniza los pronósticos
(``update_or_create``) sin duplicar nada.
"""

from django.core.management.base import (
    BaseCommand, CommandError, CommandParser)
from django.db import transaction
from django.utils import timezone

from pool.models import (
    Prediction, Quiniela, User, UserQuiniela, WindowUser)
from pool.services.evaluation import recompute_all

# JORNADA 1 = SUBGROUP_1, la fase que nace cerrada (ya jugada).
JORNADA_1_ORDER = 1


class Command(BaseCommand):
    help = (
        "Clona los pronósticos de un usuario de una quiniela a otra "
        "(excepto la jornada 1).")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "user_id", type=int, help="ID del usuario a clonar.")
        parser.add_argument(
            "--source", default="sanginiela",
            help="Slug de la quiniela origen (por defecto sanginiela).")
        parser.add_argument(
            "--target", default="bienestar",
            help="Slug de la quiniela destino (por defecto bienestar).")
        parser.add_argument(
            "--no-recompute", action="store_true",
            help="No recalcular puntajes al terminar.")

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        user = User.objects.filter(pk=options["user_id"]).first()
        if user is None:
            raise CommandError(
                f"No existe el usuario con id {options['user_id']}.")

        source = self._quiniela(options["source"])
        target = self._quiniela(options["target"])
        if source.pk == target.pk:
            raise CommandError("Origen y destino no pueden ser iguales.")

        self._ensure_membership(user, target)
        copied, windows = self._clone_predictions(user, source, target)
        self._mark_sent(user, windows)

        if not options["no_recompute"]:
            recompute_all()

        self.stdout.write(self.style.SUCCESS(
            f"«{user}»: {copied} pronósticos clonados de "
            f"'{source.slug}' a '{target.slug}', {len(windows)} ventanas "
            f"marcadas como enviadas."))

    @staticmethod
    def _quiniela(slug: str) -> Quiniela:
        quiniela = Quiniela.objects.filter(slug=slug).first()
        if quiniela is None:
            raise CommandError(f"No existe la quiniela «{slug}».")
        return quiniela

    def _ensure_membership(self, user: User, target: Quiniela) -> None:
        """Inscribe al usuario en la quiniela destino si no lo estaba.

        El signal de ``UserQuiniela`` materializa un ``WindowUser`` por
        ventana del destino, necesarios luego para marcar el envío.
        """
        _, created = UserQuiniela.objects.get_or_create(
            user=user, quiniela=target)
        if created:
            self.stdout.write(self.style.WARNING(
                f"«{user}» no estaba inscrito en «{target.slug}»; "
                f"se inscribió."))

    def _clone_predictions(
        self, user: User, source: Quiniela, target: Quiniela,
    ) -> tuple[int, set[int]]:
        """Copia los pronósticos crudos del usuario, salvo la jornada 1.

        Devuelve cuántos copió y los IDs de las ventanas destino que
        recibieron al menos un pronóstico (para marcarlas enviadas).
        """
        # stage_id -> window destino: una fase cae en una sola ventana
        # por quiniela, así ubicamos qué ventana toca cada partido.
        stage_window: dict[int, int] = {}
        for win in target.windows.prefetch_related("stages"):
            for stage in win.stages.all():
                stage_window[stage.id] = win.id

        sources = Prediction.objects.filter(
            user=user, quiniela=source,
        ).exclude(
            match__stage__order=JORNADA_1_ORDER,
        ).select_related("match")

        touched: set[int] = set()
        copied = 0
        for pred in sources:
            Prediction.objects.update_or_create(
                user=user, match_id=pred.match_id, quiniela=target,
                defaults={
                    "date": pred.date,
                    "home_goals": pred.home_goals,
                    "away_goals": pred.away_goals,
                    "advancing_team_id": pred.advancing_team_id,
                },
            )
            copied += 1
            window_id = stage_window.get(pred.match.stage_id)
            if window_id is not None:
                touched.add(window_id)
        return copied, touched

    def _mark_sent(self, user: User, window_ids: set[int]) -> None:
        """Marca enviadas las ventanas tocadas, sin pisar un envío previo."""
        if not window_ids:
            return
        WindowUser.objects.filter(
            user=user, window_id__in=window_ids, sent_at__isnull=True,
        ).update(sent_at=timezone.now())
