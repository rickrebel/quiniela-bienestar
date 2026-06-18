"""Tests del alta de jugadores por sí mismos (vista register)."""

from django.test import TestCase
from django.urls import reverse

from pool.models import StageUser, User
from tournament.models import Stage


class RegisterViewTests(TestCase):
    url = reverse("register")

    def _payload(self, **overrides) -> dict:
        data = {
            "first_name": "Ana",
            "email": "ana@example.com",
            "password": "x",
            "password_confirm": "x",
        }
        data.update(overrides)
        return data

    def test_new_user_is_created_active_and_logged_in(self):
        response = self.client.post(self.url, self._payload())
        self.assertRedirects(
            response, reverse("groups"),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email="ana@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.first_name, "Ana")
        self.assertEqual(user.username, user.email)
        self.assertTrue(user.check_password("x"))
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), user.id)

    def test_new_user_gets_stageuser_for_every_stage(self):
        Stage.objects.create(
            key="GROUP_STAGE", name="Fase de grupos",
            short_name="Grupos", order=1)
        Stage.objects.create(
            key="LAST_16", name="Octavos", short_name="Octavos", order=2)
        self.client.post(self.url, self._payload())
        user = User.objects.get(email="ana@example.com")
        self.assertEqual(StageUser.objects.filter(user=user).count(), 2)

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

    def test_preregistered_user_is_completed_without_duplicating_stageusers(
            self):
        Stage.objects.create(
            key="GROUP_STAGE", name="Fase de grupos",
            short_name="Grupos", order=1)
        # create_user dispara la señal que crea su StageUser.
        user = User.objects.create_user(
            email="ana@example.com", first_name="Preregistrada")

        response = self.client.post(
            self.url, self._payload(first_name="Ana"))
        self.assertRedirects(
            response, reverse("groups"),
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.first_name, "Ana")
        self.assertTrue(user.check_password("x"))
        self.assertEqual(StageUser.objects.filter(user=user).count(), 1)

    def test_missing_name_rejected(self):
        response = self.client.post(self.url, self._payload(first_name=""))
        self.assertContains(response, "El nombre es requerido")
