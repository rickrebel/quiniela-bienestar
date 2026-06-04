"""Modelos de la quiniela: usuarios y sus pronósticos.

Depende de la app ``tournament`` (Match, Stage) en una sola dirección:
``pool`` importa de ``tournament``, nunca al revés.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import UniqueConstraint


class UserManager(BaseUserManager):
    """Manager de usuarios que usa el email como identificador."""

    def create_user(self, email: str, **extra_fields) -> "User":
        """Crea un usuario sin contraseña usable (preregistro)."""
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str = None, **extra_fields
    ) -> "User":
        """Crea un superusuario con contraseña usable."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractUser):
    """Usuario de la quiniela; el username siempre es igual al email.

    Se sobrescribe ``username`` para quitar el UnicodeUsernameValidator,
    que rechaza el carácter '@'. ``first_name`` (heredado) guarda el
    nombre visible del jugador. ``is_active=False`` indica un usuario
    preregistrado que todavía no ha entrado.
    """

    username = models.CharField(max_length=254, unique=True)
    email = models.EmailField(unique=True)
    did_pay = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs) -> None:
        """Fuerza que el username siga siempre al email."""
        self.username = self.email
        super().save(*args, **kwargs)


class StageUser(models.Model):
    """Estado de un usuario frente a una fase del torneo.

    ``sent_at`` marca cuándo se envió el correo con sus pronósticos de la
    fase; ``closed_at``, cuándo se concluyó la revisión. Se usan DateTime
    nulables (no booleanos) para conservar también el momento del evento.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="stage_states"
    )
    stage = models.ForeignKey(
        "tournament.Stage",
        on_delete=models.PROTECT,
        related_name="user_states",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "estado de fase por usuario"
        verbose_name_plural = "estados de fase por usuario"
        constraints = [
            UniqueConstraint(
                fields=["user", "stage"],
                name="uq_stageuser_user_stage",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.stage}"


class Prediction(models.Model):
    """Pronóstico de un usuario para un partido."""

    SAVED = "saved"
    SUBMITTED = "submitted"
    STATUS_CHOICES = [
        (SAVED, "Guardada"),
        (SUBMITTED, "Enviada"),
    ]

    date = models.DateTimeField()
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="predictions"
    )
    match = models.ForeignKey(
        "tournament.Match",
        on_delete=models.CASCADE,
        related_name="predictions",
    )
    home_goals = models.IntegerField()
    away_goals = models.IntegerField()
    status = models.CharField(max_length=100, choices=STATUS_CHOICES)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "match"],
                name="uq_prediction_user_match",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.match}"
