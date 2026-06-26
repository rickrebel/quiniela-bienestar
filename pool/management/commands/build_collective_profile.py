"""Genera las predicciones del perfil virtual "Ignorancia colectiva".

Agrega las predicciones reales de una ventana —todas sus fases: la
"Grupos" de sanginiela junta los 3 subgrupos— (media recortada +
Poisson, ver ``pool/services/aggregation.py``) y las congela como
predicciones del usuario virtual, marcando el ``sent_at`` de su
``WindowUser`` y enviando su Excel como a cualquier jugador.

Solo corre tras el ``resolved_send_deadline`` de la ventana: revelar el
agregado antes del cierre rompería la independencia de las predicciones,
la condición clave de la sabiduría colectiva (Lorenz et al., PNAS 2011).
"""

from collections import defaultdict

from django.core.management.base import (
    BaseCommand, CommandError, CommandParser)
from django.db import transaction
from django.utils import timezone

from pool.models import (
    Prediction, Quiniela, UserQuiniela, Window, WindowUser)
from pool.services.aggregation import (
    VIRTUAL_NAME, AggregateResult, aggregate_score,
    get_or_create_virtual_user)
from pool.services.excel import generate_excel
from tournament.models import Match, Stage


class Command(BaseCommand):
    help = "Genera las predicciones agregadas del perfil virtual."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "order", type=int,
            help="Orden de la ventana dentro de la quiniela (1, 2, …).")
        parser.add_argument(
            "--quiniela", required=True,
            help="Slug de la quiniela cuyas predicciones se agregan.")
        parser.add_argument(
            "--force", action="store_true",
            help="Corre aunque la ventana no haya cerrado o ya se haya "
                 "generado el perfil (solo pruebas).")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Imprime la agregación sin guardar ni enviar correo.")

    def handle(self, *args, **options) -> None:
        quiniela = Quiniela.objects.filter(slug=options["quiniela"]).first()
        if quiniela is None:
            raise CommandError(
                f"No existe la quiniela {options['quiniela']}.")
        window = Window.objects.filter(
            quiniela=quiniela, order=options["order"]
        ).prefetch_related("stages").first()
        if window is None:
            raise CommandError(
                f"La quiniela {quiniela.slug} no tiene ventana "
                f"{options['order']}.")
        if not window.is_past_deadline and not options["force"]:
            raise CommandError(
                "La ventana no ha cerrado; generar el agregado antes del "
                "deadline contaminaría la independencia de las "
                "predicciones. Usa --force solo en pruebas."
            )

        # Guarda de congelado sin crear filas (respeta --dry-run): la
        # inscripción y el WindowUser se persisten solo en la corrida real.
        virtual = get_or_create_virtual_user()
        window_user = WindowUser.objects.filter(
            user=virtual, window=window).first()
        if window_user and window_user.sent_at and not options["force"]:
            raise CommandError(
                "El perfil virtual ya envió esta ventana; está congelado. "
                "Usa --force para regenerarlo (solo pruebas)."
            )

        stages = list(window.stages.all())
        by_match = self._predictions_by_match(stages, quiniela)
        matches = Match.objects.filter(stage__in=stages).select_related(
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
            # El virtual es miembro de la quiniela para entrar a su board y
            # snapshots (cada quiniela tiene su propia ignorancia colectiva);
            # el signal le materializa el WindowUser de la ventana.
            UserQuiniela.objects.get_or_create(
                user=virtual, quiniela=quiniela)
            window_user, _ = WindowUser.objects.get_or_create(
                user=virtual, window=window)
            for match_id, result in results.items():
                Prediction.objects.update_or_create(
                    user=virtual,
                    match_id=match_id,
                    quiniela=quiniela,
                    defaults={
                        "home_goals": result.home_goals,
                        "away_goals": result.away_goals,
                        "date": now,
                    },
                )
            window_user.sent_at = now
            window_user.save(update_fields=["sent_at"])
        generate_excel(virtual, window, quiniela)

        self.stdout.write(self.style.SUCCESS(
            f"Perfil «{VIRTUAL_NAME}» de {quiniela.slug} generado: "
            f"{len(results)} partidos de {window.resolved_name()}, Excel "
            f"enviado a {virtual.email}."
        ))

    def _predictions_by_match(
        self, stages: list[Stage], quiniela: Quiniela
    ) -> dict[int, tuple[list[int], list[int]]]:
        """Goles predichos por los usuarios reales, agrupados por partido."""
        rows = Prediction.objects.filter(
            match__stage__in=stages, quiniela=quiniela
        ).exclude(
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
