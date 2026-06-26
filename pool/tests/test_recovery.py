"""Tests del flujo de recuperación de contraseña (espejo de onigies)."""

from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pool.models import PasswordRecoveryToken, Quiniela, User
from pool.services.recovery import create_recovery_token


def make_user(email: str = "ana@example.com", **extra) -> User:
    user = User.objects.create_user(
        email=email, first_name="Ana", **extra)
    user.set_password("vieja-clave")
    user.is_active = True
    user.save()
    return user


class TokenModelTests(TestCase):
    def test_new_token_is_valid_and_expires_in_24h(self):
        token = create_recovery_token(make_user())
        self.assertTrue(token.is_valid())
        delta = token.expires_at - timezone.now()
        self.assertAlmostEqual(
            delta.total_seconds(), 24 * 3600, delta=60)

    def test_expired_token_is_invalid(self):
        token = create_recovery_token(make_user())
        token.expires_at = timezone.now() - timedelta(minutes=1)
        token.save()
        self.assertFalse(token.is_valid())

    def test_used_token_is_invalid(self):
        token = create_recovery_token(make_user())
        token.mark_used()
        self.assertFalse(token.is_valid())

    def test_new_request_invalidates_previous_tokens(self):
        user = make_user()
        first = create_recovery_token(user)
        second = create_recovery_token(user)
        first.refresh_from_db()
        self.assertFalse(first.is_valid())
        self.assertTrue(second.is_valid())


class ForgotPasswordViewTests(TestCase):
    url = reverse("forgot_password")

    def test_active_user_receives_email_with_link(self):
        user = make_user()
        response = self.client.post(self.url, {"email": user.email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        token = user.recovery_tokens.get()
        self.assertIn(str(token.key), mail.outbox[0].body)

    def test_unknown_email_same_response_no_email(self):
        response = self.client.post(
            self.url, {"email": "nadie@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Si el correo está registrado")
        self.assertEqual(len(mail.outbox), 0)

    def test_preregistered_user_gets_no_email(self):
        # is_active=False = nunca ha entrado: su contraseña se define
        # en el primer login, no por recuperación.
        user = User.objects.create_user(email="pre@example.com")
        response = self.client.post(self.url, {"email": user.email})
        self.assertContains(response, "Si el correo está registrado")
        self.assertEqual(len(mail.outbox), 0)

    def test_virtual_user_gets_no_email(self):
        user = make_user("colectivo@example.com", is_virtual=True)
        self.client.post(self.url, {"email": user.email})
        self.assertEqual(len(mail.outbox), 0)

    def test_email_lookup_is_case_insensitive(self):
        user = make_user()
        self.client.post(self.url, {"email": user.email.upper()})
        self.assertEqual(len(mail.outbox), 1)


class ResetPasswordViewTests(TestCase):
    def _url(self, token: PasswordRecoveryToken) -> str:
        return reverse("reset_password", kwargs={"key": token.key})

    def test_valid_token_shows_form_with_email(self):
        user = make_user()
        token = create_recovery_token(user)
        response = self.client.get(self._url(token))
        self.assertContains(response, user.email)

    def test_invalid_token_shows_notice(self):
        token = create_recovery_token(make_user())
        token.mark_used()
        response = self.client.get(self._url(token))
        self.assertContains(response, "inválido o ya expiró")

    def test_confirm_sets_password_consumes_token_and_logs_in(self):
        Quiniela.objects.create(name="Q", slug="q")
        user = make_user()
        token = create_recovery_token(user)
        payload = {
            "password": "clave-nueva-8",
            "password_confirm": "clave-nueva-8",
        }
        response = self.client.post(self._url(token), payload)
        self.assertRedirects(
            response,
            reverse("window", kwargs={"quiniela": "q", "order": 1}),
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertTrue(user.check_password("clave-nueva-8"))
        token.refresh_from_db()
        self.assertFalse(token.is_valid())
        # Auto-login: la sesión quedó autenticada.
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), user.id)

    def test_mismatched_passwords_keep_token_alive(self):
        user = make_user()
        token = create_recovery_token(user)
        payload = {
            "password": "clave-nueva-8",
            "password_confirm": "otra-cosa-123",
        }
        response = self.client.post(self._url(token), payload)
        self.assertContains(response, "no coinciden")
        token.refresh_from_db()
        self.assertTrue(token.is_valid())
        user.refresh_from_db()
        self.assertTrue(user.check_password("vieja-clave"))

    def test_short_password_rejected(self):
        token = create_recovery_token(make_user())
        payload = {"password": "corta", "password_confirm": "corta"}
        response = self.client.post(self._url(token), payload)
        self.assertContains(response, "Mínimo 8 caracteres")
