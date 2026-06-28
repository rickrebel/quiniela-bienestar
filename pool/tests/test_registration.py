"""Tests del alta de jugadores por sí mismos (vista register)."""

from django.test import TestCase
from django.urls import reverse

from pool.models import (
    Quiniela, User, UserQuiniela, Window, WindowUser)
from tournament.models import Stage


class RegisterViewTests(TestCase):
    url = reverse("register")

    def setUp(self) -> None:
        self.quiniela = Quiniela.objects.create(name="Q", slug="q")

    def _payload(self, **overrides) -> dict:
        data = {
            "first_name": "Ana",
            "email": "ana@example.com",
            "password": "x",
            "password_confirm": "x",
            "quinielas": [self.quiniela.id],
        }
        data.update(overrides)
        return data

    def test_new_user_is_created_active_and_logged_in(self):
        response = self.client.post(self.url, self._payload())
        self.assertRedirects(
            response,
            reverse("window", kwargs={"quiniela": "q", "order": 1}),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email="ana@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.first_name, "Ana")
        self.assertEqual(user.username, user.email)
        self.assertTrue(user.check_password("x"))
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), user.id)
        self.assertTrue(
            UserQuiniela.objects.filter(
                user=user, quiniela=self.quiniela).exists())

    def test_membership_created_for_each_selected_quiniela(self):
        other = Quiniela.objects.create(name="Otra", slug="otra")
        self.client.post(
            self.url, self._payload(quinielas=[self.quiniela.id, other.id]))
        user = User.objects.get(email="ana@example.com")
        self.assertEqual(
            set(UserQuiniela.objects.filter(user=user).values_list(
                "quiniela_id", flat=True)),
            {self.quiniela.id, other.id},
        )

    def test_no_quiniela_selected_rejected(self):
        response = self.client.post(self.url, self._payload(quinielas=[]))
        self.assertContains(response, "Elige al menos una quiniela")
        self.assertFalse(
            User.objects.filter(email="ana@example.com").exists())

    def test_single_char_password_is_accepted(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.get(email="ana@example.com").check_password("x"))

    def test_email_is_normalized_lowercase(self):
        self.client.post(self.url, self._payload(email="Ana@Example.com"))
        self.assertTrue(
            User.objects.filter(email="ana@example.com").exists())

    def test_mismatched_passwords_rejected(self):
        response = self.client.post(
            self.url, self._payload(password="x", password_confirm="y"))
        self.assertContains(response, "no coinciden")
        self.assertFalse(
            User.objects.filter(email="ana@example.com").exists())

    def test_duplicate_active_email_rejected(self):
        user = User.objects.create_user(
            email="ana@example.com", first_name="Otra")
        user.set_password("vieja")
        user.is_active = True
        user.save()
        response = self.client.post(self.url, self._payload())
        self.assertContains(response, "Ya existe una cuenta")
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Otra")
        self.assertTrue(user.check_password("vieja"))

    def test_virtual_email_rejected(self):
        User.objects.create_user(
            email="ana@example.com", first_name="Colectivo",
            is_virtual=True)
        response = self.client.post(self.url, self._payload())
        self.assertContains(response, "no tiene acceso")

    def test_preregistered_user_is_completed(self):
        user = User.objects.create_user(
            email="ana@example.com", first_name="Preregistrada")

        response = self.client.post(
            self.url, self._payload(first_name="Ana"))
        self.assertRedirects(
            response,
            reverse("window", kwargs={"quiniela": "q", "order": 1}),
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.first_name, "Ana")
        self.assertTrue(user.check_password("x"))

    def test_missing_name_rejected(self):
        response = self.client.post(self.url, self._payload(first_name=""))
        self.assertContains(response, "El nombre es requerido")


class WindowUserSignalTests(TestCase):
    """Inscribir a un usuario en una quiniela materializa sus WindowUser."""

    def test_membership_creates_window_user_per_window(self):
        quiniela = Quiniela.objects.create(name="Q", slug="q")
        s1 = Stage.objects.create(
            key="SUBGROUP_1", name="J1", short_name="J1", order=1,
            is_group=True)
        s2 = Stage.objects.create(
            key="LAST_32", name="16avos", short_name="16avos", order=2)
        w1 = Window.objects.create(quiniela=quiniela, order=1)
        w1.stages.add(s1)
        w2 = Window.objects.create(quiniela=quiniela, order=2)
        w2.stages.add(s2)
        user = User.objects.create_user("ana@x.com", first_name="Ana")

        UserQuiniela.objects.create(user=user, quiniela=quiniela)

        self.assertEqual(
            set(WindowUser.objects.filter(user=user).values_list(
                "window_id", flat=True)),
            {w1.id, w2.id},
        )

    def test_membership_is_idempotent(self):
        quiniela = Quiniela.objects.create(name="Q", slug="q")
        w = Window.objects.create(quiniela=quiniela, order=1)
        user = User.objects.create_user("ana@x.com", first_name="Ana")
        WindowUser.objects.create(user=user, window=w)

        UserQuiniela.objects.create(user=user, quiniela=quiniela)

        self.assertEqual(
            WindowUser.objects.filter(user=user, window=w).count(), 1)
