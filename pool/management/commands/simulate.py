"""Simula un torneo en curso con partidos reales disfrazados (solo local).

Deja la DB como si hoy fuera el día ``--day`` del Mundial (default 5):
desplaza el calendario completo para que el día 1 caiga ``day - 1`` días
atrás y, para los partidos ya "jugados", aplica resultados REALES de la
Champions 2025-26 (``db/jsons/sim/cl2025.json``, ver ``fetch_sim_source``)
reescritos como si los hubieran jugado las selecciones del fixture. Las
tarjetas se fabrican (la fuente no trae ``bookings``). Completa las
predicciones de los usuarios activos — forzando en el usuario de prueba
los 5 casos visuales de puntaje — y marca los envíos.

Si ``--day`` alcanza dieciseisavos, asigna equipos arbitrarios a los ya
"jugados" (sin resolver bracket) y al primero le toca el partido con
penales de la fuente, para iterar esa tarjeta.

Idempotente: el desplazamiento se ancla a una fecha absoluta y los
partidos ya FINISHED no se tocan (salvo ``--rebuild-results``). No hay
reset: para volver a cero, re-corre los seeds o restaura tu respaldo
(``cp db/app.sqlite3 db/app.sqlite3.bak`` antes de jugar).
"""

import json
import random
from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from pool.models import Prediction, StageUser, User
from tournament.models import Match, Stage, Team
from tournament.services.fd_results import apply_fd_result, final_goals

SOURCE_PATH = Path("db/jsons/sim/cl2025.json")

# Pesos plausibles para lo que la fuente no trae: predicciones y tarjetas.
GOAL_WEIGHTS = {0: 25, 1: 35, 2: 22, 3: 12, 4: 5, 5: 1}
YELLOW_WEIGHTS = {0: 15, 1: 35, 2: 30, 3: 15, 4: 5}
RED_PROBABILITY = 0.07

# Primer dieciseisavo de la demo (idea original: "Sudáfrica - Corea").
DEMO_FIRST_PAIR = ("RSA", "KOR")


def _weighted(rng: random.Random, weights: dict[int, int]) -> int:
    values = list(weights)
    return rng.choices(values, weights=[weights[v] for v in values])[0]


class Command(BaseCommand):
    help = (
        "Simula torneo en curso al día --day con resultados reales "
        "disfrazados (cl2025.json). Solo local; respalda antes: "
        "cp db/app.sqlite3 db/app.sqlite3.bak"
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--day", type=int, default=5,
            help="Día del Mundial que será HOY (hora local). Default: 5.")
        parser.add_argument("--seed", type=int, default=2026)
        parser.add_argument(
            "--rebuild-results", action="store_true",
            help="Regenera resultados aunque el partido ya esté FINISHED.")
        parser.add_argument(
            "--user", default="",
            help="Email del usuario que recibe los 5 casos canónicos de "
                 "puntaje (default: el primer usuario activo).")
        parser.add_argument(
            "--force", action="store_true",
            help="Permite correr aunque DEBUG sea False.")

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        self._guard_local(options["force"])
        if options["day"] < 1:
            raise CommandError("--day debe ser >= 1.")
        rng = random.Random(options["seed"])
        today = timezone.localdate()
        source = self._load_source()

        matches = list(
            Match.objects.order_by("datetime", "of_number")
            .select_related("stage", "home_team", "away_team")
        )
        if not matches:
            raise CommandError("No hay partidos; corre los seeds primero.")

        delta_days = self._shift_calendar(matches, today, options["day"])
        reset = self._reset_future(matches, today)
        forced = self._assign_knockout_teams(rng, matches, today, source)
        finished = self._apply_results(
            rng, matches, today, options["rebuild_results"], source, forced)

        deadlines = self._configure_stages(matches)
        created_su = self._sync_stage_users()
        created_preds = self._fill_predictions(rng, matches, deadlines)
        canonical = self._force_canonical(
            rng, matches, deadlines, options["user"])
        marked_sent = self._mark_sent(rng, deadlines)

        self.stdout.write(self.style.SUCCESS(
            f"Calendario desplazado {delta_days:+d} día(s) (hoy = día "
            f"{options['day']}). Resultados aplicados: {finished}, "
            f"futuros limpiados: {reset}. StageUser creados: "
            f"{created_su}. Predicciones creadas: {created_preds} "
            f"(+{canonical} canónicas). Envíos marcados: {marked_sent}."
        ))

    def _guard_local(self, force: bool) -> None:
        """Bloquea el comando fuera de local (``DEBUG`` es el proxy).

        Producción fija ``DEBUG=False``; en local es ``True``. El motor
        de BD no sirve de proxy porque en local también se usa Postgres.
        """
        if not settings.DEBUG and not force:
            msg = (
                "DEBUG=False (parece producción). Comando solo para "
                "local; usa --force si de verdad lo quieres."
            )
            raise CommandError(msg)

    def _load_source(self) -> dict:
        """Separa la fuente en pools: grupos, eliminatoria y penales."""
        if not SOURCE_PATH.exists():
            raise CommandError(
                f"Falta {SOURCE_PATH}; corre fetch_sim_source primero.")
        data = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
        finished = [m for m in data["matches"] if m["status"] == "FINISHED"]
        knockout = [m for m in finished if m["stage"] != "LEAGUE_STAGE"]
        pens = [
            m for m in knockout
            if m["score"].get("duration") == "PENALTY_SHOOTOUT"
        ]
        decisive = [
            m for m in knockout
            if m not in pens and self._plausible_knockout(m["score"])
        ]
        return {
            "group": [m for m in finished if m["stage"] == "LEAGUE_STAGE"],
            "knockout": decisive,
            "pens": pens,
        }

    @staticmethod
    def _plausible_knockout(score: dict) -> bool:
        """Filtra payloads imposibles para un cruce mundialista.

        Las idas/vueltas de CL pueden empatar a 120' sin penales, y su
        prórroga la dispara el global (no el marcador del partido), así
        que existen "5-0 EXTRA_TIME". En eliminatoria directa: sin
        empates, y al tiempo extra solo se llega empatado a los 90'.
        """
        home = final_goals(score, "home")
        away = final_goals(score, "away")
        if home == away:
            return False
        if score.get("duration") == "EXTRA_TIME":
            regular = score.get("regularTime")
            return (
                regular is not None
                and regular["home"] == regular["away"]
            )
        return True

    def _shift_calendar(self, matches: list[Match], today, day: int) -> int:
        """Ancla el día 1 a (hoy - (day-1)): re-ejecutar da delta 0."""
        current_day1 = timezone.localdate(matches[0].datetime)
        delta = (today - timedelta(days=day - 1)) - current_day1
        if delta:
            for match in matches:
                match.datetime += delta
            Match.objects.bulk_update(matches, ["datetime"], batch_size=200)
        return delta.days

    def _reset_future(self, matches: list[Match], today) -> int:
        """Limpia partidos "futuros" que quedaron jugados.

        Pasa al mover ``--day`` hacia atrás entre corridas: el resultado
        ya no corresponde. En eliminatoria también se devuelven los
        equipos de la demo a placeholder (en local todo equipo de
        eliminatoria salió de aquí; producción nunca corre esto).
        """
        count = 0
        for match in matches:
            if timezone.localdate(match.datetime) < today:
                continue
            had_teams = (
                match.stage.key != Stage.GROUP_STAGE
                and match.home_team_id is not None
            )
            if match.status != "FINISHED" and not had_teams:
                continue
            match.status = "TIMED"
            match.home_goals = match.away_goals = None
            match.home_yellow = match.away_yellow = None
            match.home_red = match.away_red = None
            match.home_penalties = match.away_penalties = None
            match.decided_by = ""
            match.raw_fd = {}
            if had_teams:
                match.home_team = match.away_team = None
            match.save()
            count += 1
        return count

    def _assign_knockout_teams(
        self, rng: random.Random, matches: list[Match], today, source: dict
    ) -> dict[int, dict]:
        """Pone equipos a los dieciseisavos ya "jugados" (sin bracket).

        Equipos arbitrarios con seed; el primer partido recibe el pair de
        la demo y el payload con penales. Devuelve {match.id: payload}
        con las fuentes forzadas.
        """
        past_l32 = [
            m for m in matches
            if m.stage.key == Stage.LAST_32
            and timezone.localdate(m.datetime) < today
        ]
        if not past_l32:
            return {}

        # El primero siempre se lleva los penales (también en rebuild).
        forced: dict[int, dict] = {}
        if source["pens"]:
            forced[past_l32[0].id] = source["pens"][0]

        pending = [m for m in past_l32 if m.home_team is None]
        if not pending:
            return forced

        teams = {t.fifa_code: t for t in Team.objects.all()}
        used = {
            t.id for m in past_l32 for t in (m.home_team, m.away_team)
            if t is not None
        }
        demo = [teams[DEMO_FIRST_PAIR[0]], teams[DEMO_FIRST_PAIR[1]]]
        free = [
            t for c, t in sorted(teams.items())
            if t.id not in used and t not in demo
        ]
        rng.shuffle(free)

        for match in pending:
            if match is past_l32[0]:
                home, away = demo
            elif len(free) >= 2:
                home, away = free.pop(), free.pop()
            else:
                break
            match.home_team, match.away_team = home, away
            match.save(update_fields=["home_team", "away_team"])
        return forced

    def _apply_results(
        self, rng: random.Random, matches: list[Match], today,
        rebuild: bool, source: dict, forced: dict[int, dict],
    ) -> int:
        count = 0
        for match in matches:
            if timezone.localdate(match.datetime) >= today:
                continue
            if match.home_team is None or match.away_team is None:
                continue
            if match.status == "FINISHED" and not rebuild:
                continue
            is_group = match.stage.key == Stage.GROUP_STAGE
            pool = source["group"] if is_group else source["knockout"]
            payload = forced.get(match.id) or rng.choice(pool)
            # Tarjetas antes de aplicar: apply_fd_result hace el save.
            match.home_yellow = _weighted(rng, YELLOW_WEIGHTS)
            match.away_yellow = _weighted(rng, YELLOW_WEIGHTS)
            match.home_red = int(rng.random() < RED_PROBABILITY)
            match.away_red = int(rng.random() < RED_PROBABILITY)
            apply_fd_result(match, self._disguise(payload, match))
            count += 1
        return count

    def _disguise(self, payload: dict, match: Match) -> dict:
        """Reescribe un payload fuente como si fuera el partido 2026."""
        fake = json.loads(json.dumps(payload))
        for side, team in (
            ("homeTeam", match.home_team), ("awayTeam", match.away_team),
        ):
            fake[side] = {
                "id": team.fd_id, "name": team.name, "tla": team.fifa_code,
            }
        fake["id"] = match.fd_id
        fake["utcDate"] = match.datetime.isoformat()
        fake["stage"] = match.stage.key
        is_group = match.stage.key == Stage.GROUP_STAGE
        fake["group"] = (
            f"GROUP_{match.home_team.group_name}" if is_group else None
        )
        fake["simulated"] = True
        for noise in ("area", "competition", "season", "odds", "referees"):
            fake.pop(noise, None)
        return fake

    def _configure_stages(self, matches: list[Match]) -> dict:
        """Abre y cierra las fases simuladas; {key: deadline}.

        Regla (ver reglas.html): cada fase cierra a las 11:59 pm del día
        previo a su primer partido, hora local. Grupos siempre; LAST_32
        solo si la demo le asignó equipos.
        """
        deadlines: dict[str, datetime] = {}
        keys = [Stage.GROUP_STAGE]
        if any(
            m.stage.key == Stage.LAST_32 and m.home_team_id
            for m in matches
        ):
            keys.append(Stage.LAST_32)
        for key in keys:
            first = next(m for m in matches if m.stage.key == key)
            day_before = timezone.localdate(first.datetime) - timedelta(
                days=1)
            deadline = timezone.make_aware(
                datetime.combine(day_before, time(23, 59)))
            Stage.objects.filter(key=key).update(
                opens_at=deadline - timedelta(days=30),
                send_deadline=deadline,
            )
            deadlines[key] = deadline
        return deadlines

    def _sync_stage_users(self) -> int:
        stages = list(Stage.objects.all())
        existing = set(StageUser.objects.values_list("user_id", "stage_id"))
        to_create = [
            StageUser(user=user, stage=stage)
            for user in User.objects.all()
            for stage in stages
            if (user.id, stage.id) not in existing
        ]
        StageUser.objects.bulk_create(to_create)
        return len(to_create)

    def _predictable(
        self, matches: list[Match], deadlines: dict
    ) -> list[Match]:
        """Partidos con equipos en las fases simuladas (las cerradas)."""
        return [
            m for m in matches
            if m.stage.key in deadlines and m.home_team_id and m.away_team_id
        ]

    def _fill_predictions(
        self, rng: random.Random, matches: list[Match], deadlines: dict
    ) -> int:
        """Completa las predicciones de los usuarios activos.

        Respeta las existentes; los inactivos no predicen (quedan LOCKED).
        """
        targets = self._predictable(matches, deadlines)
        existing = set(Prediction.objects.values_list("user_id", "match_id"))
        to_create = []
        for user in User.objects.filter(is_active=True):
            for match in targets:
                if (user.id, match.id) in existing:
                    continue
                deadline = deadlines[match.stage.key]
                to_create.append(Prediction(
                    user=user,
                    match=match,
                    home_goals=_weighted(rng, GOAL_WEIGHTS),
                    away_goals=_weighted(rng, GOAL_WEIGHTS),
                    date=deadline - timedelta(
                        minutes=rng.randint(10, 700)),
                ))
        Prediction.objects.bulk_create(to_create)
        return len(to_create)

    def _force_canonical(
        self, rng: random.Random, matches: list[Match], deadlines: dict,
        email: str,
    ) -> int:
        """Garantiza los 5 casos visuales de puntaje al usuario de prueba.

        Sobre los primeros grupos terminados: exacto con ganador (5),
        exacto en empate (4), ganador+diferencia (4), solo resultado (3)
        y fallo (0). Cada caso toma el primer partido compatible.
        """
        user = (
            User.objects.filter(email=email).first() if email
            else User.objects.filter(is_active=True).order_by("id").first()
        )
        if user is None:
            return 0
        finished = [
            m for m in self._predictable(matches, deadlines)
            if m.stage.key == Stage.GROUP_STAGE and m.status == "FINISHED"
        ]
        cases = {
            "exact_win": lambda h, a: (h, a) if h != a else None,
            "exact_draw": lambda h, a: (h, a) if h == a else None,
            "diff": lambda h, a: (h + 1, a + 1) if h != a else None,
            "result_only": lambda h, a: (h + 2, a) if h > a
            else ((h, a + 2) if h < a else (h + 1, a + 1)),
            "miss": lambda h, a: (a, h) if h != a else (h + 1, a),
        }
        count = 0
        for match in finished:
            if not cases:
                break
            for name, build in list(cases.items()):
                pred = build(match.home_goals, match.away_goals)
                if pred is None:
                    continue
                deadline = deadlines[match.stage.key]
                Prediction.objects.update_or_create(
                    user=user, match=match,
                    defaults={
                        "home_goals": pred[0], "away_goals": pred[1],
                        "date": deadline - timedelta(
                            minutes=rng.randint(10, 700)),
                    },
                )
                del cases[name]
                count += 1
                break
        return count

    def _mark_sent(self, rng: random.Random, deadlines: dict) -> int:
        """Marca envíos pendientes y corrige los que quedaron obsoletos.

        Tras re-anclar el calendario el deadline puede haber retrocedido,
        dejando ``sent_at`` posteriores a él; se regeneran también.
        """
        count = 0
        for key, deadline in deadlines.items():
            rows = StageUser.objects.filter(
                Q(sent_at__isnull=True) | Q(sent_at__gt=deadline),
                stage__key=key,
                user__is_active=True,
            )
            for row in rows:
                row.sent_at = deadline - timedelta(
                    minutes=rng.randint(5, 600))
                row.save(update_fields=["sent_at"])
                count += 1
        return count
