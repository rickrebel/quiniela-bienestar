"""Tests del routing por path /<slug>/ y del render de window_view.

Smoke tests que ejercen las plantillas (tabs, secciones, posiciones) para
atrapar errores de ``{% url %}`` o de contexto, más la resolución de la
quiniela por dominio y los redirects de compatibilidad.
"""

import json
from datetime import timedelta

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from pool.models import Quiniela, User, UserQuiniela, Window, WindowUser
from pool.views.scope import quiniela_for_host
from tournament.models import Match, Stadium, Stage, Team


class QuinielaForHostTests(SimpleTestCase):
    @override_settings(
        QUINIELA_DOMAINS={"sanginiela.test": "sanginiela"},
        DEFAULT_QUINIELA_SLUG="bienestar",
    )
    def test_maps_known_host(self):
        self.assertEqual(
            quiniela_for_host("sanginiela.test:8000"), "sanginiela")

    @override_settings(
        QUINIELA_DOMAINS={"sanginiela.test": "sanginiela"},
        DEFAULT_QUINIELA_SLUG="bienestar",
    )
    def test_unknown_host_falls_to_default(self):
        self.assertEqual(quiniela_for_host("otro.test"), "bienestar")


class WindowViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.group_stage = Stage.objects.create(
            key="SUBGROUP_1", name="Jornada 1", short_name="J1", order=1,
            is_group=True, opens_at=now - timedelta(days=1),
            send_deadline=now + timedelta(days=1),
        )
        cls.knockout = Stage.objects.create(
            key="QUARTER_FINALS", name="Cuartos", short_name="Cuartos",
            order=4, opens_at=now - timedelta(days=1),
            send_deadline=now + timedelta(days=1),
        )
        cls.stadium = Stadium.objects.create(
            name="Azteca", city="CDMX", country="mx", utc_offset=-6)
        cls.a1 = Team.objects.create(
            name="Mexico", name_es="México", fifa_code="MEX",
            group_name="A", confederation="concacaf")
        cls.a2 = Team.objects.create(
            name="Canada", name_es="Canadá", fifa_code="CAN",
            group_name="A", confederation="concacaf")
        cls.group_match = Match.objects.create(
            datetime=now, stage=cls.group_stage, stadium=cls.stadium,
            home_team=cls.a1, away_team=cls.a2, of_number=1)
        cls.ko_match = Match.objects.create(
            datetime=now, stage=cls.knockout, stadium=cls.stadium,
            of_number=57, home_placeholder="W1", away_placeholder="W2")

        cls.quiniela = Quiniela.objects.create(name="Q", slug="q")
        cls.w_groups = Window.objects.create(
            quiniela=cls.quiniela, order=1, name="Grupos", short_name="Grupos")
        cls.w_groups.stages.add(cls.group_stage)
        cls.w_ko = Window.objects.create(quiniela=cls.quiniela, order=2)
        cls.w_ko.stages.add(cls.knockout)

        cls.user = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True)
        UserQuiniela.objects.create(user=cls.user, quiniela=cls.quiniela)

    def setUp(self):
        self.client.force_login(self.user)

    def test_membership_materialized_window_users(self):
        self.assertEqual(
            WindowUser.objects.filter(user=self.user).count(), 2)

    def test_groups_tab_renders(self):
        response = self.client.get("/q/grupos/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grupo A")

    def test_group_window_redirects_to_groups(self):
        # La ventana de grupo no se entra por order: cae al tab canónico.
        response = self.client.get("/q/ventana/1/")
        self.assertRedirects(
            response, "/q/grupos/", fetch_redirect_response=False)

    def test_knockout_window_renders(self):
        self.assertEqual(self.client.get("/q/ventana/2/").status_code, 200)

    def test_other_pages_render(self):
        for path in ("/q/posiciones/", "/q/calendario/", "/q/reglas/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_unknown_quiniela_404(self):
        self.assertEqual(self.client.get("/nope/ventana/1/").status_code, 404)

    def test_unknown_window_404(self):
        self.assertEqual(self.client.get("/q/ventana/9/").status_code, 404)

    def test_root_redirects_to_member_window(self):
        response = self.client.get("/")
        self.assertRedirects(
            response, "/q/ventana/1/", fetch_redirect_response=False)

    def test_legacy_path_redirects_under_slug(self):
        response = self.client.get("/posiciones/")
        self.assertRedirects(
            response, "/q/posiciones/", fetch_redirect_response=False)

    def test_legacy_stage_key_redirects_to_calendar(self):
        response = self.client.get("/stage/LAST_16/")
        self.assertRedirects(
            response, "/q/calendario/", fetch_redirect_response=False)

    def test_send_window_marks_window_user(self):
        # Autoguarda el único partido de la ventana de grupos y la envía.
        self.client.post(
            f"/q/prediction/{self.group_match.id}/",
            json.dumps({"home_goals": 1, "away_goals": 0}),
            content_type="application/json")
        response = self.client.post(
            "/q/send/", json.dumps({"window": 1}),
            content_type="application/json")
        self.assertEqual(response.status_code, 200)
        wu = WindowUser.objects.get(user=self.user, window=self.w_groups)
        self.assertIsNotNone(wu.sent_at)


class GroupTabCollapseTests(TestCase):
    """Bienestar: 3 ventanas de grupo (una por jornada) colapsan en un tab.

    Verifica que la presentación (un tab "Grupos") se desacopla del envío
    (3 ventanas), y que ``groups_view`` escoge la jornada vigente.
    """

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        # J1 cerrada (vencida), J2 viva, J3 aún sin abrir.
        spans = {
            "SUBGROUP_1": (now - timedelta(days=3), now - timedelta(days=2)),
            "SUBGROUP_2": (now - timedelta(days=1), now + timedelta(days=1)),
            "SUBGROUP_3": (now + timedelta(days=2), now + timedelta(days=3)),
        }
        cls.stadium = Stadium.objects.create(
            name="Azteca", city="CDMX", country="mx", utc_offset=-6)
        cls.a1 = Team.objects.create(
            name="Mexico", name_es="México", fifa_code="MEX",
            group_name="A", confederation="concacaf")
        cls.a2 = Team.objects.create(
            name="Canada", name_es="Canadá", fifa_code="CAN",
            group_name="A", confederation="concacaf")
        cls.quiniela = Quiniela.objects.create(name="Bienestar", slug="b")
        cls.windows = {}
        for i, (key, (opens, deadline)) in enumerate(spans.items(), start=1):
            stage = Stage.objects.create(
                key=key, name=f"Jornada {i}", short_name=f"J{i}", order=i,
                is_group=True, opens_at=opens, send_deadline=deadline)
            # El kickoff cae al cierre de la ventana, no a su apertura: un
            # partido ya iniciado se bloquea aunque su ventana siga viva
            # (candado por partido), así que la jornada viva necesita un
            # partido todavía futuro para seguir siendo editable.
            Match.objects.create(
                datetime=deadline, stage=stage, stadium=cls.stadium,
                home_team=cls.a1, away_team=cls.a2, of_number=i)
            window = Window.objects.create(quiniela=cls.quiniela, order=i)
            window.stages.add(stage)
            cls.windows[key] = window
        cls.user = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True)
        UserQuiniela.objects.create(user=cls.user, quiniela=cls.quiniela)

    def setUp(self):
        self.client.force_login(self.user)

    def test_single_grupos_tab(self):
        response = self.client.get("/b/grupos/")
        self.assertEqual(response.status_code, 200)
        group_tabs = [t for t in response.context["tabs"] if t["is_groups"]]
        self.assertEqual(len(group_tabs), 1)
        self.assertEqual(group_tabs[0]["key"], "grupos")

    def test_active_window_is_live_jornada(self):
        response = self.client.get("/b/grupos/")
        # J1 vencida y J3 sin abrir: la vigente es J2 (order 2).
        self.assertEqual(response.context["window"].order, 2)
        self.assertEqual(response.context["state"], WindowUser.EDITING)

    def test_only_live_jornada_editable(self):
        response = self.client.get("/b/grupos/")
        editable = {
            m.stage.key: m.editable
            for s in response.context["sections"] for m in s["matches"]
        }
        self.assertTrue(editable["SUBGROUP_2"])
        self.assertFalse(editable["SUBGROUP_1"])
        self.assertFalse(editable["SUBGROUP_3"])
