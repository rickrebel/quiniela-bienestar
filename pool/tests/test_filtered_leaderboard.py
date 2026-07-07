"""Tests del leaderboard filtrado ("Mini leaderboard").

Cubre ``resolve_filter`` por ámbito (incluidos los inválidos),
``build_leaderboard`` acotado por ``match_ids`` y el view
``filtered_board_view`` (fragmento, 400 y login requerido).
"""

from datetime import datetime, timezone as dt_tz

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from pool.models import Prediction, Quiniela, User, UserQuiniela
from pool.services.evaluation import recompute_all
from pool.services.leaderboard import (
    build_leaderboard,
    filter_options,
    resolve_filter,
)
from tournament.models import Match, Stadium, Stage, Team


def _utc(*args):
    return datetime(*args, tzinfo=dt_tz.utc)


class FilteredLeaderboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")
        cls.quiniela = Quiniela.objects.get(slug="bienestar")
        cls.group_stage = Stage.objects.create(
            key="SUBGROUP_1", name="Jornada 1", short_name="J1",
            color="#4CAF50", order=1, is_group=True,
        )
        cls.knockout = Stage.objects.create(
            key="LAST_16", name="Octavos", short_name="Octavos",
            color="#2196F3", order=4,
        )
        cls.stadium = Stadium.objects.create(
            name="Azteca", city="CDMX", country="mx", utc_offset=-6,
        )
        cls.team_a = Team.objects.create(
            name="Mexico", name_es="México", fifa_code="MEX", group_name="A",
            confederation="concacaf", flag_code="mx",
        )
        cls.team_b = Team.objects.create(
            name="Canada", name_es="Canadá", fifa_code="CAN", group_name="A",
            confederation="concacaf", flag_code="ca",
        )
        cls.team_c = Team.objects.create(
            name="Brazil", name_es="Brasil", fifa_code="BRA", group_name="B",
            confederation="conmebol", flag_code="br",
        )

        # Local de sede (offset -6): m_g1 el 11-jun, m_g2 el 12-jun, m_ko el
        # 13-jun. m_g1/m_g2 son de grupo (home = México, grupo A); m_ko es
        # eliminatoria (Brasil vs Canadá).
        cls.m_g1 = cls._match(
            cls.group_stage, cls.team_a, cls.team_b, 1,
            _utc(2026, 6, 11, 18, 0), 2, 1)
        cls.m_g2 = cls._match(
            cls.group_stage, cls.team_a, cls.team_b, 2,
            _utc(2026, 6, 12, 18, 0), 0, 0)
        cls.m_ko = cls._match(
            cls.knockout, cls.team_c, cls.team_b, 57,
            _utc(2026, 6, 13, 18, 0), 1, 0)

        cls.ana = cls._enroll(User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True))
        cls.beto = cls._enroll(User.objects.create_user(
            "beto@x.com", first_name="Beto", is_active=True))

        # Ana: m_g1 exacto (5), m_g2 empate exacto (4), m_ko exacto (5) = 14.
        cls._pred(cls.ana, cls.m_g1, 2, 1)
        cls._pred(cls.ana, cls.m_g2, 0, 0)
        cls._pred(cls.ana, cls.m_ko, 1, 0)
        # Beto: solo m_g1, solo resultado (3).
        cls._pred(cls.beto, cls.m_g1, 1, 0)
        recompute_all()

    @classmethod
    def _match(cls, stage, home, away, of_number, dt, hg, ag):
        return Match.objects.create(
            datetime=dt, stage=stage, stadium=cls.stadium,
            home_team=home, away_team=away, of_number=of_number,
            home_goals=hg, away_goals=ag, status="FINISHED",
        )

    @classmethod
    def _enroll(cls, user):
        UserQuiniela.objects.get_or_create(user=user, quiniela=cls.quiniela)
        return user

    @classmethod
    def _pred(cls, user, match, home, away):
        return Prediction.objects.create(
            user=user, quiniela=cls.quiniela, match=match,
            home_goals=home, away_goals=away, date=timezone.now(),
        )

    # ----- resolve_filter -------------------------------------------------

    def test_resolve_fase(self):
        ids, label = resolve_filter(
            self.quiniela, "fase", str(self.group_stage.id))
        self.assertEqual(set(ids), {self.m_g1.id, self.m_g2.id})
        self.assertEqual(label, "Jornada 1")

    def test_resolve_fecha_uses_local_date(self):
        ids, label = resolve_filter(self.quiniela, "fecha", "2026-06-11")
        self.assertEqual(ids, [self.m_g1.id])
        self.assertEqual(label, "jueves 11 de junio")

    def test_resolve_equipo(self):
        ids, label = resolve_filter(
            self.quiniela, "equipo", str(self.team_b.id))
        # Canadá juega los tres partidos.
        self.assertEqual(set(ids), {self.m_g1.id, self.m_g2.id, self.m_ko.id})
        self.assertEqual(label, "Canadá")

    def test_resolve_grupo_only_group_matches(self):
        ids, label = resolve_filter(self.quiniela, "grupo", "A")
        # El cruce de eliminatoria queda fuera (is_group=False).
        self.assertEqual(set(ids), {self.m_g1.id, self.m_g2.id})
        self.assertEqual(label, "Grupo A")

    def test_resolve_invalid_ambito(self):
        with self.assertRaises(ValueError):
            resolve_filter(self.quiniela, "bogus", "1")

    def test_resolve_invalid_fase(self):
        with self.assertRaises(ValueError):
            resolve_filter(self.quiniela, "fase", "999999")

    def test_resolve_invalid_grupo(self):
        with self.assertRaises(ValueError):
            resolve_filter(self.quiniela, "grupo", "Z")

    # ----- build_leaderboard con match_ids --------------------------------

    def test_partial_sum_over_subset(self):
        ids, _ = resolve_filter(
            self.quiniela, "fase", str(self.group_stage.id))
        board = build_leaderboard(
            self.quiniela, match_ids=ids, with_trends=False)
        # Ana solo suma m_g1 (5) + m_g2 (4) = 9 en el corte de grupos.
        self.assertEqual(board.row_for(self.ana).points, 9)
        # 5 (ganador m_g1) + 4 (empate m_g2) = 9.
        self.assertEqual(board.max_points, 9)

    def test_full_board_sums_all(self):
        board = build_leaderboard(self.quiniela, with_trends=False)
        self.assertEqual(board.row_for(self.ana).points, 14)
        self.assertEqual(board.max_points, 14)

    def test_no_trends_when_disabled(self):
        board = build_leaderboard(self.quiniela, with_trends=False)
        row = board.row_for(self.ana)
        self.assertIsNone(row.trend_batch)
        self.assertIsNone(row.trend_day)

    def test_dense_ranking_and_virtual_on_subset(self):
        virtual = self._enroll(User.objects.create_user(
            "colectivo@x.com", first_name="Ignorancia colectiva",
            is_virtual=True))
        self._pred(virtual, self.m_g1, 3, 1)  # solo resultado (3)
        recompute_all()
        board = build_leaderboard(
            self.quiniela, match_ids=[self.m_g1.id], with_trends=False)
        rows = {r.user: r for r in board.rows}
        # Ana 5 (1°), Beto y virtual 3; Beto es 2°, el virtual sin posición.
        self.assertEqual(rows[self.ana].position, 1)
        self.assertEqual(rows[self.beto].position, 2)
        self.assertEqual(rows[virtual].position, 0)

    def test_empty_subset_leaves_no_players(self):
        board = build_leaderboard(
            self.quiniela, match_ids=[], with_trends=False)
        self.assertFalse(any(r.has_played for r in board.rows))
        self.assertEqual(board.max_points, 0)

    def test_filter_options_shape(self):
        options = filter_options(self.quiniela)
        self.assertEqual(
            [s["name"] for s in options["stages"]], ["Jornada 1", "Octavos"])
        self.assertEqual(
            [g["letter"] for g in options["groups"]], ["A", "B"])
        self.assertEqual(options["date_min"], "2026-06-11")
        self.assertEqual(options["date_max"], "2026-06-13")
        # Hoy (posterior al mundial de prueba) se acota al máximo del rango.
        self.assertEqual(options["date_default"], "2026-06-13")
        self.assertTrue(all("flag" in t for t in options["teams"]))
        # Fechas con partidos (local de sede), ordenadas y sin duplicados:
        # alimentan las flechas prev/next del título.
        self.assertEqual(
            options["dates"], ["2026-06-11", "2026-06-12", "2026-06-13"])

    def test_group_options_flags_in_real_order(self):
        options = filter_options(self.quiniela)
        group_a = options["groups"][0]
        # México (4 pts reales) va antes que Canadá (1 pt).
        self.assertEqual(
            group_a["flags"],
            ["/static/flags_40/mx.png", "/static/flags_40/ca.png"],
        )

    # ----- view -----------------------------------------------------------

    def test_view_requires_login(self):
        response = self.client.get("/bienestar/posiciones/filtrado/")
        self.assertEqual(response.status_code, 302)

    def test_view_renders_fragment(self):
        self.client.force_login(self.ana)
        response = self.client.get(
            "/bienestar/posiciones/filtrado/",
            {"ambito": "fase", "valor": str(self.group_stage.id)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtro: Jornada 1")
        self.assertContains(response, "data-filter-ambito")
        # El dialog no lleva checkbox "Filtrar": siempre hay filtro.
        self.assertNotContains(response, "data-filter-enable")
        # Con filtro activo el título trae flechas prev/next y el
        # contenedor emite las fechas navegables.
        self.assertContains(response, "data-filter-nav")
        self.assertContains(response, "filtered-date-options")

    def test_view_full_board_has_no_nav(self):
        self.client.force_login(self.ana)
        response = self.client.get(
            "/bienestar/posiciones/filtrado/", {"part": "board"})
        # Sin filtro_label ("Leaderboard completo") no hay qué navegar.
        self.assertNotContains(response, "data-filter-nav")

    def test_posiciones_has_inline_filter_row(self):
        self.client.force_login(self.ana)
        response = self.client.get("/bienestar/posiciones/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-filter-enable")
        self.assertContains(response, "data-inline-board")
        self.assertContains(response, "filtered-group-options")

    def test_view_part_board_only_region(self):
        self.client.force_login(self.ana)
        response = self.client.get(
            "/bienestar/posiciones/filtrado/", {"part": "board"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leaderboard completo")
        # part=board no trae la fila de filtro.
        self.assertNotContains(response, "data-filter-ambito")

    def test_view_bad_params_400(self):
        self.client.force_login(self.ana)
        response = self.client.get(
            "/bienestar/posiciones/filtrado/",
            {"ambito": "fase", "valor": "999999"})
        self.assertEqual(response.status_code, 400)
