"""Genera las predicciones del perfil virtual "Ignorancia colectiva".

Agrega las predicciones reales de una fase (media recortada + Poisson,
ver ``pool/services/aggregation.py``) y las congela como predicciones
del usuario virtual, marcando su ``sent_at`` y enviando su Excel como
a cualquier jugador.

Solo corre tras el ``send_deadline`` de la fase: revelar el agregado
antes del cierre rompería la independencia de las predicciones, la
condición clave de la sabiduría colectiva (Lorenz et al., PNAS 2011).
"""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import (
    BaseCommand, CommandError, CommandParser)
from django.db import transaction
from django.utils import timezone

from pool.models import Prediction, StageUser
from pool.services.aggregation import (
    VIRTUAL_EMAIL, VIRTUAL_NAME, AggregateResult, aggregate_score)
from pool.services.excel import generate_excel
from tournament.models import Match, Stage

User = get_user_model()


class Command(BaseCommand):
    help = "Genera las predicciones agregadas del perfil virtual."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "stage_key", help="Clave de la fase (p. ej. GROUP_STAGE).")
        parser.add_argument(
            "--force", action="store_true",
            help="Corre aunque la fase no haya cerrado o ya se haya "
                 "generado el perfil (solo pruebas).")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Imprime la agregación sin guardar ni enviar correo.")

    def handle(self, *args, **options) -> None:
        stage = Stage.objects.filter(key=options["stage_key"]).first()
        if stage is None:
            raise CommandError(f"No existe la fase {options['stage_key']}.")
        if not stage.is_past_deadline and not options["force"]:
            raise CommandError(
                "La fase no ha cerrado; generar el agregado antes del "
                "deadline contaminaría la independencia de las "
                "predicciones. Usa --force solo en pruebas."
            )

        virtual = self._get_virtual_user()
        stage_user, _ = StageUser.objects.get_or_create(
            user=virtual, stage=stage)
        if stage_user.sent_at and not options["force"]:
            raise CommandError(
                "El perfil virtual ya envió esta fase; está congelado. "
                "Usa --force para regenerarlo (solo pruebas)."
            )

        by_match = self._predictions_by_match(stage)
        matches = Match.objects.filter(stage=stage).select_related(
            "home_team", "away_team").order_by("datetime", "of_number")

        results: dict[int, AggregateResult] = {}
        for match in matches:
            preds = by_match.get(match.id)
            if not preds:
                self.stdout.write(self.style.WARNING(
                    f"{match}: sin predicciones, se omite."
                ))
                continue
            home_preds, away_preds = preds
            result = aggregate_score(home_preds, away_preds)
            results[match.id] = result
            self._report(match, result, len(home_preds))

        if not results:
            raise CommandError("Ningún partido tenía predicciones.")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                "Dry run: no se guardó ni se envió nada."
            ))
            return

        now = timezone.now()
        with transaction.atomic():
            for match_id, result in results.items():
                Prediction.objects.update_or_create(
                    user=virtual,
                    match_id=match_id,
                    defaults={
                        "home_goals": result.home_goals,
                        "away_goals": result.away_goals,
                        "date": now,
                    },
                )
            stage_user.sent_at = now
            stage_user.save(update_fields=["sent_at"])
        generate_excel(virtual, stage)

        self.stdout.write(self.style.SUCCESS(
            f"Perfil «{VIRTUAL_NAME}» generado: {len(results)} partidos "
            f"de {stage.name}, Excel enviado a {virtual.email}."
        ))

    def _get_virtual_user(self) -> User:
        """Usuario virtual, creándolo en el primer uso.

        ``create_user`` deja contraseña inusable e ``is_active=False``;
        junto con la guarda de ``login_view`` nadie puede entrar con él.
        La señal post_save le materializa sus StageUser.
        """
        user = User.objects.filter(email=VIRTUAL_EMAIL).first()
        if user is None:
            user = User.objects.create_user(
                email=VIRTUAL_EMAIL,
                first_name=VIRTUAL_NAME,
                is_virtual=True,
            )
        return user

    def _predictions_by_match(
        self, stage: Stage
    ) -> dict[int, tuple[list[int], list[int]]]:
        """Goles predichos por los usuarios reales, agrupados por partido."""
        rows = Prediction.objects.filter(match__stage=stage).exclude(
            user__is_virtual=True
        ).values_list("match_id", "home_goals", "away_goals")
        grouped: dict[int, tuple[list[int], list[int]]] = defaultdict(
            lambda: ([], []))
        for match_id, home, away in rows:
            grouped[match_id][0].append(home)
            grouped[match_id][1].append(away)
        return grouped

    def _report(
        self, match: Match, result: AggregateResult, n_preds: int
    ) -> None:
        top = ", ".join(
            f"{h}-{a} {p:.1%}" for h, a, p in result.ranked[:3]
        )
        self.stdout.write(
            f"{match} [{n_preds} predicciones] "
            f"λ {result.lam_home:.2f}-{result.lam_away:.2f} → "
            f"{result.home_goals}-{result.away_goals}  (top: {top})"
        )
