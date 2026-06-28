"""Candado por partido: un partido ya iniciado no admite cambios.

La editabilidad de la ventana sigue abierta (``opens_at`` pasado,
``send_deadline`` futuro), pero el kickoff de un partido concreto lo cierra
de forma independiente. Cubre el autoguardado por partido y el chequeo de
completitud al enviar.
"""

import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pool.models import Prediction, Quiniela, User, UserQuiniela, Window
from tournament.models import Match, Stadium, Stage, Team


class MatchLockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        # Ventana de 16vos abierta y sin vencer: la editabilidad de ventana
        # no es lo que bloquea aquí, sino el kickoff de cada partido.
        cls.knockout = Stage.objects.create(
            key="LAST_32", name="Dieciseisavos", short_name="16avos",
            color="#2196F3", order=2,
            opens_at=now - timedelta(days=1),
            send_deadline=now + timedelta(days=1),
        )
        cls.quiniela = Quiniela.objects.create(name="Q", slug="q")
        cls.window = Window.objects.create(quiniela=cls.quiniela, order=1)
        cls.window.stages.add(cls.knockout)
        cls.stadium = Stadium.objects.create(
            name="Estadio Azteca", city="CDMX", country="mx", utc_offset=-6,
        )
        cls.team_a = Team.objects.create(
            name="Mexico", name_es="México", fifa_code="MEX", group_name="A",
            confederation="concacaf",
        )
        cls.team_b = Team.objects.create(
            name="Canada", name_es="Canadá", fifa_code="CAN", group_name="A",
            confederation="concacaf",
        )
        # Mismo (window, stage): uno ya comenzado, otro futuro.
        cls.started = Match.objects.create(
            datetime=now - timedelta(minutes=10), stage=cls.knockout,
            stadium=cls.stadium, home_team=cls.team_a, away_team=cls.team_b,
            of_number=73,
        )
        cls.future = Match.objects.create(
            datetime=now + timedelta(days=2), stage=cls.knockout,
            stadium=cls.stadium, home_team=cls.team_a, away_team=cls.team_b,
            of_number=74,
        )
        cls.player = User.objects.create_user(
            "ana@x.com", first_name="Ana", is_active=True,
        )
        UserQuiniela.objects.create(user=cls.player, quiniela=cls.quiniela)

    def setUp(self):
        self.client.force_login(self.player)

    def _save(self, match, payload):
        return self.client.post(
            f"/q/prediction/{match.id}/",
            json.dumps(payload), content_type="application/json",
        )

    def test_has_started_property(self):
        self.assertTrue(self.started.has_started)
        self.assertFalse(self.future.has_started)

    def test_autosave_started_rejected(self):
        resp = self._save(self.started, {"home_goals": 1, "away_goals": 0})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(
            Prediction.objects.filter(
                user=self.player, match=self.started).exists())

    def test_autosave_future_allowed(self):
        resp = self._save(self.future, {"home_goals": 2, "away_goals": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            Prediction.objects.filter(
                user=self.player, match=self.future).exists())

    def test_send_ignores_started_match(self):
        # Solo el futuro está lleno; el ya iniciado queda sin pronóstico.
        self._save(self.future, {"home_goals": 2, "away_goals": 1})
        resp = self.client.post(
            "/q/send/", json.dumps({"window": self.window.order}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
