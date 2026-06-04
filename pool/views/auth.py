"""Vistas de autenticación sin contraseña (acceso por correo)."""

from django.contrib.auth import get_user_model, login, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from pool.forms import EmailAccessForm

User = get_user_model()

# Backend explícito para login() (evita ambigüedad si hay varios).
_AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


def login_view(request: HttpRequest) -> HttpResponse:
    """Acceso por correo en una sola pantalla, sin contraseña.

    GET: muestra el formulario de email.
    POST: valida el email; si el usuario no existe, agrega un error
    pidiendo preregistrar. Si existe, lo activa (en caso de estar
    preregistrado), inicia sesión y redirige a 'grupos'.
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
            else:
                if not user.is_active:
                    user.is_active = True
                    user.save()
                login(request, user, backend=_AUTH_BACKEND)
                return redirect("grupos")
    else:
        form = EmailAccessForm()

    return render(request, "auth/login.html", {"form": form})


def logout_view(request: HttpRequest) -> HttpResponse:
    """Cierra la sesión y redirige a la pantalla de acceso."""
    logout(request)
    return redirect("login")
