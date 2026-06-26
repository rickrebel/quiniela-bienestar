"""Vistas de autenticación sin contraseña (acceso por correo)."""

import logging

from django.contrib.auth import get_user_model, login, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from pool.forms import (
    EmailAccessForm, RecoveryConfirmForm, RecoveryRequestForm,
    RegistrationForm)
from pool.models import PasswordRecoveryToken
from pool.services.recovery import (
    create_recovery_token, recovery_url, send_recovery_email)
from pool.views.scope import home_slug

User = get_user_model()
logger = logging.getLogger(__name__)

# Mensaje único pase lo que pase: no revela si el correo existe.
RECOVERY_SENT_MSG = (
    "Si el correo está registrado, recibirás un enlace en breve."
)

# Backend explícito para login() (evita ambigüedad si hay varios).
_AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


def login_view(request: HttpRequest) -> HttpResponse:
    """Acceso por correo en una sola pantalla, sin contraseña.

    GET: muestra el formulario de email.
    POST: valida el email; si el usuario no existe, agrega un error
    pidiendo preregistrar. Si existe, lo activa (en caso de estar
    preregistrado), inicia sesión y redirige a la fase de grupos.
    """
    if request.method == "POST":
        form = EmailAccessForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            user = User.objects.filter(email=email).first()
            if user is None:
                form.add_error(
                    "email",
                    "Es necesario preregistrar el email",
                )
            elif user.is_virtual:
                # Sin esta guarda, el flujo de primer login de abajo
                # dejaría "secuestrar" al perfil agregado adoptando
                # cualquier contraseña tecleada.
                form.add_error("email", "Este perfil no tiene acceso")
            else:
                if user.is_active:
                    if user.check_password(form.cleaned_data["password"]):
                        login(request, user, backend=_AUTH_BACKEND)
                        return redirect(
                            "window", quiniela=home_slug(request), order=1)
                    else:
                        form.add_error("password", "Contraseña incorrecta")
                else:
                    user.set_password(form.cleaned_data["password"])
                    user.is_active = True
                    user.save()
                    login(request, user, backend=_AUTH_BACKEND)
                    return redirect(
                        "window", quiniela=home_slug(request), order=1)
    else:
        form = EmailAccessForm()

    return render(request, "auth/login.html", {"form": form})


def register_view(request: HttpRequest) -> HttpResponse:
    """Alta de un jugador por sí mismo.

    GET: muestra el formulario de registro.
    POST: valida nombre, email y contraseña. Si el email ya tiene cuenta
    activa (o es un perfil virtual) lo rechaza; si existe un preregistro
    sin estrenar lo completa; en otro caso crea el usuario. Al terminar
    inicia sesión y redirige a la primera ventana.
    """
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            first_name = form.cleaned_data["first_name"]
            user = User.objects.filter(email__iexact=email).first()
            if user is not None and user.is_virtual:
                form.add_error("email", "Este perfil no tiene acceso")
            elif user is not None and user.is_active:
                form.add_error(
                    "email", "Ya existe una cuenta con este email")
            else:
                if user is None:
                    user = User.objects.create_user(
                        email=email, first_name=first_name)
                else:
                    # Preregistro sin estrenar: solo falta la contraseña.
                    user.first_name = first_name
                user.set_password(form.cleaned_data["password"])
                user.is_active = True
                user.save()
                login(request, user, backend=_AUTH_BACKEND)
                return redirect(
                    "window", quiniela=home_slug(request), order=1)
    else:
        form = RegistrationForm()

    return render(request, "auth/register.html", {"form": form})


def logout_view(request: HttpRequest) -> HttpResponse:
    """Cierra la sesión y redirige a la pantalla de acceso."""
    logout(request)
    return redirect("login")


def forgot_password_view(request: HttpRequest) -> HttpResponse:
    """Pide el correo y manda el link de recuperación.

    La respuesta es siempre la misma (anti-enumeración). Sin link
    para preregistrados (su contraseña se define en el primer login)
    ni para el perfil virtual.
    """
    sent = False
    if request.method == "POST":
        form = RecoveryRequestForm(request.POST)
        if form.is_valid():
            user = User.objects.filter(
                email__iexact=form.cleaned_data["email"],
                is_active=True,
                is_virtual=False,
            ).first()
            if user:
                token = create_recovery_token(user)
                try:
                    url = recovery_url(token, request)
                    send_recovery_email(user, url)
                except Exception:
                    # El error de SMTP se loguea pero no se filtra al
                    # usuario: la respuesta debe seguir siendo genérica.
                    logger.exception(
                        "Error enviando correo de recuperación a %s",
                        user.email,
                    )
            sent = True
    else:
        form = RecoveryRequestForm()

    context = {
        "form": form,
        "sent_message": RECOVERY_SENT_MSG if sent else "",
    }
    return render(request, "auth/forgot_password.html", context)


def reset_password_view(request: HttpRequest, key) -> HttpResponse:
    """Formulario de nueva contraseña para un token vigente.

    Token inexistente, usado o expirado → misma pantalla con aviso y
    link para pedir otro. Al confirmar: contraseña nueva, token
    consumido y auto-login (igual que el primer login).
    """
    token = PasswordRecoveryToken.objects.select_related("user").filter(
        key=key).first()
    if token is None or not token.is_valid():
        return render(
            request, "auth/reset_password.html", {"invalid": True})

    if request.method == "POST":
        form = RecoveryConfirmForm(request.POST)
        if form.is_valid():
            user = token.user
            user.set_password(form.cleaned_data["password"])
            user.is_active = True
            user.save()
            token.mark_used()
            login(request, user, backend=_AUTH_BACKEND)
            return redirect(
                "window", quiniela=home_slug(request), order=1)
    else:
        form = RecoveryConfirmForm()

    context = {"form": form, "email": token.user.email}
    return render(request, "auth/reset_password.html", context)
