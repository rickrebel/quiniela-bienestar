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


class Team(models.Model):
    """Selección participante en el torneo."""

    name = models.CharField(max_length=100, unique=True)
    flag = models.CharField(
        max_length=100, unique=True, null=True, blank=True)
    group_name = models.CharField(max_length=1)
    points = models.IntegerField(null=True, blank=True)
    won_games = models.IntegerField(null=True, blank=True)
    draws = models.IntegerField(null=True, blank=True)
    out_goals = models.IntegerField(null=True, blank=True)
    in_goals = models.IntegerField(null=True, blank=True)
    red_cards = models.IntegerField(null=True, blank=True)
    yellow_cards = models.IntegerField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class Match(models.Model):
    """Partido del torneo entre dos selecciones."""

    date = models.DateTimeField()
    phase = models.CharField(max_length=100)
    group_name = models.CharField(max_length=1, null=True, blank=True)
    stadium = models.CharField(max_length=100, null=True, blank=True)
    team_a = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="matches_as_a")
    team_b = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name="matches_as_b")
    goals_a = models.IntegerField(null=True, blank=True)
    goals_b = models.IntegerField(null=True, blank=True)
    match_number = models.IntegerField(null=True, blank=True)


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
        User, on_delete=models.CASCADE, related_name="predictions")
    match = models.ForeignKey(
        "Match", on_delete=models.CASCADE, related_name="predictions")
    goals_a = models.IntegerField()
    goals_b = models.IntegerField()
    status = models.CharField(max_length=100, choices=STATUS_CHOICES)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "match"],
                name="uq_prediction_user_match",
            ),
        ]
