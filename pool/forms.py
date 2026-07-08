"""Formularios de la app quiniela."""

from django import forms

from pool.models import Quiniela


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


class RegistrationForm(forms.Form):
    """Alta de un jugador por sí mismo: nombre, email y contraseña.

    La contraseña no tiene mínimo de caracteres (solo no vacía) pero sí
    confirmación. La unicidad del email se valida en la vista para
    distinguir cuenta activa de preregistro sin estrenar.
    """

    first_name = forms.CharField(
        label="Nombre",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
        error_messages={"required": "El nombre es requerido"},
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "username"}),
        error_messages={
            "required": "El email es requerido",
            "invalid": "Ingresa un correo válido",
        },
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
        error_messages={"required": "La contraseña es requerida"},
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
        error_messages={"required": "Confirma la contraseña"},
    )
    quinielas = forms.ModelMultipleChoiceField(
        label="¿A qué quinielas te inscribes?",
        # El queryset real se fija en __init__ para evaluar el cierre
        # (timezone.now) por request, no al importar el módulo.
        queryset=Quiniela.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Elige al menos una quiniela"},
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Solo quinielas con registro abierto: un id cerrado enviado a mano
        # cae en "opción no válida" al no estar en el queryset.
        self.fields["quinielas"].queryset = (
            Quiniela.objects.open_for_registration())

    def clean_first_name(self) -> str:
        return self.cleaned_data["first_name"].strip()

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()

    def clean(self) -> dict:
        data = super().clean()
        password = data.get("password")
        confirm = data.get("password_confirm")
        if password and confirm and password != confirm:
            self.add_error(
                "password_confirm", "Las contraseñas no coinciden")
        return data


class RecoveryRequestForm(forms.Form):
    """Solicitud del link de recuperación: solo el correo."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "username"}),
        error_messages={
            "required": "El email es requerido",
            "invalid": "Ingresa un correo válido",
        },
    )

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()


class RecoveryConfirmForm(forms.Form):
    """Nueva contraseña con confirmación (mínimo 8, como onigies)."""

    password = forms.CharField(
        label="Nueva contraseña",
        min_length=8,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
        error_messages={
            "required": "La contraseña es requerida",
            "min_length": "Mínimo 8 caracteres",
        },
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
        error_messages={"required": "Confirma la contraseña"},
    )

    def clean(self) -> dict:
        data = super().clean()
        password = data.get("password")
        confirm = data.get("password_confirm")
        if password and confirm and password != confirm:
            self.add_error(
                "password_confirm", "Las contraseñas no coinciden")
        return data
