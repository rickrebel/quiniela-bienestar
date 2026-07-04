"""Tests del payload del dialog de partido (agrupación y privacidad)."""

from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from pool.models import Prediction, Quiniela, User
from pool.services.evaluation import ScorelineEval
from pool.services.match_dialog import (
    build_match_dialog_payload,
    diff_label,
    group_predictions,
    points_display,
)
from tournament.models import Match, Stadium, Stage, Team


def _row(name: str, home: int, away: int, is_self: bool = False) -> dict:
    return {"name": name, "home": home, "away": away, "is_self": is_self}


class GroupPredictionsTests(SimpleTestCase):
    def test_groups_ordered_by_diff_descending(self):
        rows = [_row("a", 0, 2), _row("b", 3, 0), _row("c", 1, 1),
                _row("d", 2, 1)]
        groups = group_predictions(rows)
        self.assertEqual([g["diff"] for g in groups], [3, 1, 0, -2])

    def test_subgroups_by_exact_score_total_descending(self):
        rows = [_row("a", 1, 0), _row("b", 3, 2), _row("c", 2, 1)]
        groups = group_predictions(rows)
        self.assertEqual(len(groups), 1)
        scores = [(s["home"], s["away"]) for s in groups[0]["subgroups"]]
        self.assertEqual(scores, [(3, 2), (2, 1), (1, 0)])

    def test_same_score_shares_subgroup_in_input_order(self):
        rows = [_row("ana", 2, 1), _row("beto", 2, 1), _row("caro", 2, 1)]
        groups = group_predictions(rows)
        subgroups = groups[0]["subgroups"]
        self.assertEqual(len(subgroups), 1)
        names = [n["name"] for n in subgroups[0]["names"]]
        self.assertEqual(names, ["ana", "beto", "caro"])

    def test_empty_input(self):
        self.assertEqual(group_predictions([]), [])


class DiffLabelTests(SimpleTestCase):
    def test_plural(self):
        self.assertEqual(diff_label(2), "+2 goles")

    def test_singular_uses_magnitude(self):
        self.assertEqual(diff_label(-1), "+1 gol")

    def test_draw(self):
        self.assertEqual(diff_label(0), "Empate")


class PointsDisplayTests(SimpleTestCase):
    def test_none_without_result(self):
        self.assertIsNone(points_display(None))

    def test_miss(self):
        display = points_display(
            ScorelineEval(points=Decimal(0), base=0, codes=[]))
        self.assertEqual(display, {"total": Decimal(0), "base": 0,
                                   "bonus": False, "kind": "miss"})

    def test_hit_with_diff_bonus_splits_base(self):
        display = points_display(ScorelineEval(
            points=Decimal(4), base=4, codes=["RESULT", "DIFF"]))
        self.assertEqual(display, {"total": Decimal(4), "base": 3,
                                   "bonus": True, "kind": "hit"})

    def test_exact(self):
        display = points_display(ScorelineEval(
            points=Decimal(5), base=5, codes=["RESULT", "DIFF", "EXACT"]))
        self.assertEqual(display, {"total": Decimal(5), "base": 5,
                                   "bonus": False, "kind": "exact"})


class DialogPayloadPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")
        cls.bienestar = Quiniela.objects.get(slug="bienestar")
        now = timezone.now()
        cls.open_stage = Stage.objects.create(
            key="GROUP_STAGE", name="Fase de grupos", short_name="grupos",
            color="#4CAF50", order=1, is_group=True,
            send_deadline=now + timedelta(days=1),
        )
        cls.closed_stage = Stage.objects.create(
            key="LAST_32", name="Dieciseisavos", short_name="16avos",
            color="#2196F3", order=2, send_deadline=now - timedelta(days=1),
        )
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
        cls.open_match = Match.objects.create(
            datetime=now, stage=cls.open_stage, stadium=cls.stadium,
            home_team=cls.team_a, away_team=cls.team_b, of_number=1,
        )
        cls.closed_match = Match.objects.create(
            datetime=now, stage=cls.closed_stage, stadium=cls.stadium,
            home_team=cls.team_a, away_team=cls.team_b, of_number=73,
            status="FINISHED", home_goals=2, away_goals=1,
        )
        cls.ana = User.objects.create_user("ana@x.com", first_name="Ana",
                                           is_active=True)
        cls.beto = User.objects.create_user("beto@x.com", first_name="Beto",
                                            is_active=True)
        for user, match, home, away in (
            (cls.ana, cls.open_match, 1, 0),
            (cls.beto, cls.open_match, 0, 0),
            (cls.ana, cls.closed_match, 2, 1),
            (cls.beto, cls.closed_match, 0, 1),
        ):
            Prediction.objects.create(user=user, match=match,
                                      quiniela=cls.bienestar,
                                      home_goals=home, away_goals=away,
                                      date=now)

    def _payload_for(self, match):
        matches = list(
            Match.objects.filter(id=match.id).select_related(
                "stage", "stadium", "home_team", "away_team"
            )
        )
        return build_match_dialog_payload(matches, self.ana, self.bienestar)[0]

    def test_open_stage_hides_predictions(self):
        payload = self._payload_for(self.open_match)
        self.assertFalse(payload["revealed"])
        self.assertNotIn("groups", payload)

    def _names(self, payload):
        return [n for g in payload["groups"]
                for s in g["subgroups"] for n in s["names"]]

    def test_closed_stage_includes_everyone(self):
        payload = self._payload_for(self.closed_match)
        self.assertTrue(payload["revealed"])
        self.assertEqual({n["name"] for n in self._names(payload)},
                         {"Ana", "Beto"})

    def test_is_self_flags_requesting_user(self):
        payload = self._payload_for(self.closed_match)
        flags = {n["name"]: n["is_self"] for n in self._names(payload)}
        self.assertEqual(flags, {"Ana": True, "Beto": False})

    def test_finished_match_scores_subgroups(self):
        payload = self._payload_for(self.closed_match)
        points = {}
        for g in payload["groups"]:
            for s in g["subgroups"]:
                for n in s["names"]:
                    points[n["name"]] = s["points"]["total"]
                    self.assertEqual(len(s["chips"]), 3)
        self.assertEqual(points["Ana"], 5)  # exacto 2-1
        self.assertEqual(points["Beto"], 0)

    def test_group_labels(self):
        payload = self._payload_for(self.closed_match)
        self.assertEqual([g["diff"] for g in payload["groups"]], [1, -1])
        self.assertEqual([g["label"] for g in payload["groups"]],
                         ["+1 gol", "+1 gol"])

    def test_is_knockout_follows_stage(self):
        self.assertFalse(self._payload_for(self.open_match)["is_knockout"])
        self.assertTrue(self._payload_for(self.closed_match)["is_knockout"])

    def test_can_record_requires_permission(self):
        self.assertFalse(self._payload_for(self.open_match)["can_record"])

    def test_can_record_with_flag_only_if_not_finished(self):
        self.ana.can_record_results = True
        self.ana.save()
        self.assertTrue(self._payload_for(self.open_match)["can_record"])
        # Terminado: ya no se ofrece la captura.
        self.assertFalse(self._payload_for(self.closed_match)["can_record"])

    def test_superuser_can_record_without_flag(self):
        self.ana.is_superuser = True
        self.ana.save()
        self.assertTrue(self._payload_for(self.open_match)["can_record"])


class PenaltySplitGateTests(TestCase):
    """El subgrupo de empates se parte por equipo de avance solo si la
    quiniela tiene la regla PENALTY (bienestar), no en la original."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_rules")
        cls.bienestar = Quiniela.objects.get(slug="bienestar")
        cls.sanginiela = Quiniela.objects.get(slug="sanginiela")
        now = timezone.now()
        cls.stage = Stage.objects.create(
            key="LAST_16", name="Octavos", short_name="8avos",
            color="#2196F3", order=3, send_deadline=now - timedelta(days=1),
        )
        cls.stadium = Stadium.objects.create(
            name="Azteca", city="CDMX", country="mx", utc_offset=-6)
        cls.mex = Team.objects.create(
            name="Mexico", name_es="México", fifa_code="MEX",
            group_name="A", confederation="concacaf")
        cls.can = Team.objects.create(
            name="Canada", name_es="Canadá", fifa_code="CAN",
            group_name="A", confederation="concacaf")
        cls.match = Match.objects.create(
            datetime=now, stage=cls.stage, stadium=cls.stadium,
            home_team=cls.mex, away_team=cls.can, of_number=89,
            status="FINISHED", home_goals=1, away_goals=1,
            decided_by=Match.PENALTY_SHOOTOUT,
            home_penalties=4, away_penalties=2,
        )
        # Partido aún no jugado, pero con deadline pasado (predicciones
        # reveladas): el reparto por avance debe verse sin puntos.
        cls.pending = Match.objects.create(
            datetime=now, stage=cls.stage, stadium=cls.stadium,
            home_team=cls.mex, away_team=cls.can, of_number=90,
        )
        cls.ana = User.objects.create_user("ana@x.com", first_name="Ana",
                                           is_active=True)
        cls.beto = User.objects.create_user("beto@x.com", first_name="Beto",
                                            is_active=True)
        # Ambos predicen empate 1-1; Ana cree que pasa MEX, Beto que pasa CAN.
        for quiniela in (cls.bienestar, cls.sanginiela):
            for match in (cls.match, cls.pending):
                Prediction.objects.create(
                    user=cls.ana, match=match, quiniela=quiniela,
                    home_goals=1, away_goals=1, advancing_team=cls.mex,
                    date=now)
                Prediction.objects.create(
                    user=cls.beto, match=match, quiniela=quiniela,
                    home_goals=1, away_goals=1, advancing_team=cls.can,
                    date=now)

    def _draw_groups(self, quiniela, match=None):
        match = match or self.match
        matches = list(Match.objects.filter(id=match.id).select_related(
            "stage", "stadium", "home_team", "away_team"))
        payload = build_match_dialog_payload(matches, self.ana, quiniela)[0]
        return [g for g in payload["groups"] if g["diff"] == 0]

    def test_splits_when_quiniela_has_penalty(self):
        # Dos grupos grandes de empate, uno por equipo que avanza (local
        # primero); el reparto va en el encabezado, no por subgrupo.
        groups = self._draw_groups(self.bienestar)
        self.assertEqual([g["advancing_side"] for g in groups],
                         ["home", "away"])
        self.assertEqual([g["advancing_code"] for g in groups],
                         ["MEX", "CAN"])
        for g in groups:
            for sub in g["subgroups"]:
                self.assertNotIn("advancing_label", sub)

    def test_no_split_without_penalty_rule(self):
        groups = self._draw_groups(self.sanginiela)
        self.assertEqual(len(groups), 1)
        self.assertNotIn("advancing_side", groups[0])
        self.assertEqual(groups[0]["label"], "Empate")
        names = {n["name"] for s in groups[0]["subgroups"]
                 for n in s["names"]}
        self.assertEqual(names, {"Ana", "Beto"})

    def test_splits_before_match_played_without_points(self):
        groups = self._draw_groups(self.bienestar, self.pending)
        self.assertEqual([g["advancing_code"] for g in groups],
                         ["MEX", "CAN"])
        # Aún sin jugar: reparto visible, pero sin puntos.
        for g in groups:
            self.assertTrue(all(s["points"] is None for s in g["subgroups"]))
