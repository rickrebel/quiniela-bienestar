"""Formularios de la app quiniela."""

from django import forms


class EmailAccessForm(forms.Form):
    """Formulario de acceso por correo, sin contraseña.

    Una sola pantalla: el usuario ingresa su email y, si ya está
    preregistrado, se le da acceso directo.
    """

    email = forms.EmailField(
        label="Email",
        # autocomplete="username" (no "email") es el valor que los
        # gestores de contraseñas emparejan con current-password.
        widget=forms.EmailInput(attrs={"autocomplete": "username"}),
        error_messages={
            "required": "El email es requerido",
            "invalid": "Ingresa un correo válido",
        },
    )

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password"}
        ),
        error_messages={
            "required": "La contraseña es requerida"
        }
    )
