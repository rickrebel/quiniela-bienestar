"""Crea la quiniela "Predicciones libres": un sandbox abierto.

Clona los periodos de ``sanginiela`` (mismas ventanas, fases y peso),
inscribe a TODOS los usuarios (virtual incluido) y siembra a cada quien
con sus pronósticos reales tomados de cualquier quiniela. Las ventanas
nacen abiertas (``opens_at`` el 20-jun) y sin envío (``sent_at`` vacío);
el plazo se fija a un centinela lejano para que nunca se bloqueen y
puedan reeditar grupos, terceros y eliminatorias a voluntad.

Idempotente: re-correrlo resincroniza quiniela, reglas, ventanas,
membresías y pronósticos (``update_or_create``/``ignore_conflicts``).

Requiere ``load_rules`` (catálogo de reglas) y la quiniela origen ya
sembrada con sus ventanas (``seed_windows``).
"""

from datetime import datetime
from datetime import timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pool.models import (
    Prediction,
    Quiniela,
    QuinielaRule,
    Rule,
    User,
    UserQuiniela,
    Window,
    WindowUser,
)
from pool.services.evaluation import recompute_all

SLUG = "libres"
NAME = "Predicciones libres"
THEME = "bosque"
SOURCE_SLUG = "sanginiela"  # de aquí se clonan las ventanas (periodos)
RULES = {"RESULT": 3, "DIFF": 1, "EXACT": 1, "PENALTY": 1}

# 20-jun 00:00 CDMX (UTC-6). Como hoy ya es posterior, todo nace abierto.
OPENS_AT = datetime(2026, 6, 20, 6, 0, tzinfo=dt_timezone.utc)
# Centinela lejano en vez de null: las ventanas 1:1 (eliminatorias) caen
# por fallback al Stage.send_deadline cuando el campo está vacío, así que
# dejarlo null NO quita el plazo; un futuro lejano sí lo neutraliza.
NO_DEADLINE = datetime(2030, 1, 1, tzinfo=dt_timezone.utc)

# Desempate del slug a preferir cuando dos predicciones quedan empatadas
# en timestamp efectivo (caso rarísimo).
TIE_PREFER_SLUG = "bienestar"


class Command(BaseCommand):
    help = 'Crea/resincroniza la quiniela "Predicciones libres".'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--no-recompute",
            action="store_true",
            help="No recalcular puntajes al terminar.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        quiniela = self._sync_quiniela()
        self._sync_rules(quiniela)
        self._clone_windows(quiniela)
        enrolled = self._enroll_all_users(quiniela)
        copied = self._copy_predictions(quiniela)

        if not options["no_recompute"]:
            recompute_all()

        self.stdout.write(self.style.SUCCESS(
            f"'{NAME}' lista: {quiniela.windows.count()} ventanas, "
            f"{enrolled} inscritos, {copied} pronósticos sembrados."))

    def _sync_quiniela(self) -> Quiniela:
        quiniela, _ = Quiniela.objects.update_or_create(
            slug=SLUG, defaults={"name": NAME, "theme": THEME})
        return quiniela

    def _sync_rules(self, quiniela: Quiniela) -> None:
        rules = {r.code: r for r in Rule.objects.all()}
        for code, points in RULES.items():
            rule = rules.get(code)
            if rule is None:
                raise CommandError(
                    f"Falta la regla '{code}' en el catálogo; "
                    f"corre load_rules.")
            QuinielaRule.objects.update_or_create(
                quiniela=quiniela, rule=rule,
                defaults={"points": points})

    def _clone_windows(self, quiniela: Quiniela) -> None:
        """Replica las ventanas de la quiniela origen, abiertas y sin plazo.

        Lee las ventanas en vivo (no hardcode) para que cualquier ajuste
        del agrupamiento origen se herede. ``opens_at``/``send_deadline``
        se fijan explícitos (ver constantes) para vencer el fallback al
        Stage de las ventanas 1:1.
        """
        source = Quiniela.objects.filter(slug=SOURCE_SLUG).first()
        if source is None:
            raise CommandError(
                f"No existe la quiniela origen '{SOURCE_SLUG}'.")

        for src in source.windows.prefetch_related("stages"):
            window, _ = Window.objects.update_or_create(
                quiniela=quiniela, order=src.order,
                defaults={
                    "name": src.name,
                    "short_name": src.short_name,
                    "color": src.color,
                    "multiplier": src.multiplier,
                    "opens_at": OPENS_AT,
                    "send_deadline": NO_DEADLINE,
                },
            )
            window.stages.set(list(src.stages.all()))

    def _enroll_all_users(self, quiniela: Quiniela) -> int:
        """Inscribe a todos los usuarios y materializa sus WindowUser.

        ``bulk_create`` con ``ignore_conflicts`` no dispara el signal de
        UserQuiniela, así que los WindowUser se aseguran a mano aquí
        (sent_at queda en null = ventana editable, nunca enviada).
        """
        users = list(User.objects.all())
        UserQuiniela.objects.bulk_create(
            [UserQuiniela(user=u, quiniela=quiniela) for u in users],
            ignore_conflicts=True,
        )
        windows = list(quiniela.windows.all())
        WindowUser.objects.bulk_create(
            [WindowUser(user=u, window=w) for u in users for w in windows],
            ignore_conflicts=True,
        )
        return len(users)

    def _copy_predictions(self, quiniela: Quiniela) -> int:
        """Siembra a cada usuario con su pronóstico más reciente "enviado".

        Por cada (usuario, partido) gana la predicción de mayor timestamp
        efectivo = ``WindowUser.sent_at`` de la ventana que cubre el
        partido (si se envió), o ``Prediction.date`` (último guardado) si
        la ventana no se envió. Empate exacto: gana ``TIE_PREFER_SLUG``.
        Así la J1 (vacía en bienestar) cae a sanginiela sin perder el
        ``advancing_team`` cuando bienestar sí trae la versión más nueva.
        """
        # (quiniela_id, stage_id) -> Window: en qué ventana de cada
        # quiniela origen cae un partido, para ubicar su sent_at.
        stage_window: dict[tuple[int, int], Window] = {}
        windows = Window.objects.exclude(quiniela=quiniela).prefetch_related(
            "stages")
        for win in windows:
            for stage in win.stages.all():
                stage_window[(win.quiniela_id, stage.id)] = win

        # (user_id, window_id) -> sent_at de las ventanas origen.
        sent_at: dict[tuple[int, int], datetime] = {
            (wu.user_id, wu.window_id): wu.sent_at
            for wu in WindowUser.objects.exclude(
                window__quiniela=quiniela)
            if wu.sent_at is not None
        }

        prefer_id = Quiniela.objects.filter(
            slug=TIE_PREFER_SLUG).values_list("id", flat=True).first()

        # Mejor candidato por (user_id, match_id): (Prediction, efectivo).
        best: dict[tuple[int, int], tuple[Prediction, datetime]] = {}
        sources = Prediction.objects.exclude(
            quiniela=quiniela).select_related("match")
        for pred in sources:
            win = stage_window.get((pred.quiniela_id, pred.match.stage_id))
            effective = pred.date
            if win is not None:
                effective = sent_at.get((pred.user_id, win.id)) or pred.date
            key = (pred.user_id, pred.match_id)
            current = best.get(key)
            if current is None or self._wins(
                pred, effective, current, prefer_id):
                best[key] = (pred, effective)

        for pred, _ in best.values():
            Prediction.objects.update_or_create(
                user_id=pred.user_id,
                match_id=pred.match_id,
                quiniela=quiniela,
                defaults={
                    "date": pred.date,
                    "home_goals": pred.home_goals,
                    "away_goals": pred.away_goals,
                    "advancing_team_id": pred.advancing_team_id,
                },
            )
        return len(best)

    @staticmethod
    def _wins(
        pred: Prediction,
        effective: datetime,
        current: tuple[Prediction, datetime],
        prefer_id: int | None,
    ) -> bool:
        """¿``pred`` desplaza al candidato actual para ese (user, match)?"""
        cur_pred, cur_eff = current
        if effective != cur_eff:
            return effective > cur_eff
        # Empate exacto: gana la quiniela preferida.
        return (
            pred.quiniela_id == prefer_id
            and cur_pred.quiniela_id != prefer_id
        )