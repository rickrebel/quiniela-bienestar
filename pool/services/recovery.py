"""Tokens de recuperación de contraseña y su correo (texto plano).

Flujo adaptado de onigies: al solicitar un link se invalidan los
tokens vivos del usuario y se emite uno nuevo; el correo es texto
plano con la URL, validez de 24 horas y un solo uso.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone

from pool.models import PasswordRecoveryToken, User

logger = logging.getLogger(__name__)


def create_recovery_token(user: User) -> PasswordRecoveryToken:
    """Invalida los tokens vivos del usuario y emite uno nuevo.

    Marcar como usados (en vez de borrar) conserva el rastro de
    cuántas veces se pidió recuperación.
    """
    now = timezone.now()
    user.recovery_tokens.filter(
        used_at__isnull=True, expires_at__gt=now
    ).update(used_at=now)
    return PasswordRecoveryToken.objects.create(user=user)


def recovery_url(token: PasswordRecoveryToken, request) -> str:
    """URL absoluta del link de recuperación.

    ``SITE_URL`` manda cuando está definida: detrás de ngrok el Host
    llega reescrito a localhost y ``build_absolute_uri`` armaría un
    link inservible fuera de esta máquina.
    """
    path = reverse("reset_password", kwargs={"key": token.key})
    base = getattr(settings, "SITE_URL", "")
    if base:
        return f"{base.rstrip('/')}{path}"
    return request.build_absolute_uri(path)


def send_recovery_email(user: User, url: str) -> None:
    """Correo sencillo de texto plano con el link de recuperación."""
    name = user.first_name or user.email
    body = (
        f"Hola {name},\n\n"
        "Recibimos una solicitud para restablecer tu contraseña de la "
        "sanginiela. Entra a este enlace para crear una nueva:\n\n"
        f"{url}\n\n"
        f"El enlace es válido por "
        f"{PasswordRecoveryToken.EXPIRY_HOURS} horas y solo puede "
        "usarse una vez.\n"
        "Si tú no lo pediste, ignora este correo: tu contraseña "
        "actual no cambia.\n"
    )
    message = EmailMessage(
        subject="Recupera tu contraseña · Sanginiela",
        body=body,
        to=[user.email],
    )
    message.send()
