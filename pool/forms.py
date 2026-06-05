"""Formularios de la app quiniela."""

from django import forms


class EmailAccessForm(forms.Form):
    """Formulario de acceso por correo, sin contraseña.

    Una sola pantalla: el usuario ingresa su email y, si ya está
    preregistrado, se le da acceso directo.
    """

    email = forms.EmailField(
        label="Email",
        error_messages={
            "required": "El email es requerido",
            "invalid": "Ingresa un correo válido",
        },
    )

    password = forms.CharField(
        label="Contraseña",
        error_messages={
            "required": "La contraseña es requerida"
        }
    )
