"""Modelos de la quiniela: usuarios y sus pronósticos."""

import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import UniqueConstraint
from django.utils import timezone
from tournament.models import Stage, Match, Team


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
    is_active = models.BooleanField(default=False)
    is_virtual = models.BooleanField(
        default=False,
        help_text=(
            "Perfil agregado (Ignorancia colectiva): visible, sin "
            "login y fuera de premios."
        ),
    )
    can_record_results = models.BooleanField(
        default=False,
        help_text=(
            "Puede capturar a mano el resultado oficial de un "
            "partido terminado."
        ),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs) -> None:
        """Fuerza que el username siga siempre al email."""
        self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return self.first_name or self.username


class PasswordRecoveryToken(models.Model):
    """Token de un solo uso para restablecer la contraseña.

    Diseño tomado de onigies: UUID propio en BD en lugar del
    ``PasswordResetTokenGenerator`` de Django, para tener expiración
    explícita, un solo uso (``used_at``) y poder invalidar los tokens
    previos del usuario al emitir uno nuevo.
    """

    EXPIRY_HOURS = 24

    key = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="recovery_tokens")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "token de recuperación"
        verbose_name_plural = "tokens de recuperación"

    def __str__(self) -> str:
        return f"{self.user} · {self.key}"

    def save(self, *args, **kwargs) -> None:
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                hours=self.EXPIRY_HOURS)
        super().save(*args, **kwargs)

    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() < self.expires_at

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])


class Rule(models.Model):
    """Catálogo global de reglas de puntuación posibles.

    Aquí vive la *definición y presentación* de cada regla
    """

    code = models.CharField(
        max_length=20, unique=True,
        help_text="Estable: RESULT, DIFF, EXACT, PENALTY.")
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=20)
    icon = models.CharField(
        max_length=40, blank=True,
        help_text="Nombre del Material Symbol o del ícono local.")
    description = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "regla"
        verbose_name_plural = "reglas"
        ordering = ["order"]

    def __str__(self) -> str:
        return self.code


# Paletas pre-armadas (temas daisyUI en assets/css/source.css). El slug
# selecciona el tema vía <html data-theme>; el color es el base-100 de
# cada tema, usado en la meta theme-color del navegador.
THEME_CHOICES = [
    ("sanginiela", "Sanginiela — azul marino + oro"),
    ("medianoche", "Medianoche — azul profundo + champaña"),
    ("bienestar", "Bienestar — guinda (gobierno federal)"),
    ("bosque", "Bosque — esmeralda"),
    ("violeta", "Violeta — ciruela"),
]


class Quiniela(models.Model):
    """Variante de quiniela (original, bienestar, …).

    Cada quiniela es independiente: reglas, pronósticos, puntajes,
    ventanas y membresías. El scoring opera por quiniela explícita (la
    activa la fija el path ``/<slug>/``).
    """

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=40, unique=True)
    theme = models.CharField(
        max_length=20,
        choices=THEME_CHOICES,
        default="sanginiela",
        help_text="Paleta de color con la que se pinta la quiniela.",
    )
    rules = models.ManyToManyField(
        Rule, through="QuinielaRule", related_name="quinielas")

    class Meta:
        verbose_name = "quiniela"
        verbose_name_plural = "quinielas"

    def __str__(self) -> str:
        return self.name


class QuinielaRule(models.Model):
    """Qué reglas aplican a una quiniela y con cuántos puntos base.

    El intermedio del M2M ``Quiniela.rules``: permite que la misma regla
    del catálogo valga distinto en cada quiniela y que PENALTY exista en
    el catálogo pero no se enlace en la quiniela original.
    """

    quiniela = models.ForeignKey(
        Quiniela, on_delete=models.CASCADE, related_name="quiniela_rules")
    rule = models.ForeignKey(
        Rule, on_delete=models.PROTECT, related_name="quiniela_rules")
    points = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "regla de quiniela"
        verbose_name_plural = "reglas de quiniela"
        ordering = ["quiniela", "rule__order"]
        constraints = [
            UniqueConstraint(
                fields=["quiniela", "rule"],
                name="uq_quinielarule_quiniela_rule",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quiniela.slug}:{self.rule.code}={self.points}"


class UserQuiniela(models.Model):
    """Membresía de un usuario en una quiniela.

    Un usuario puede estar en varias quinielas a la vez; cada membresía es
    independiente. ``authorized`` ("pagó y envió a tiempo") es por quiniela
    (antes vivía global en ``User.authorized``).
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="quiniela_memberships")
    quiniela = models.ForeignKey(
        Quiniela, on_delete=models.CASCADE, related_name="memberships")
    authorized = models.BooleanField(
        default=False,
        help_text="Pagó y envió a tiempo; se marca a mano.",
    )
    history_compare = models.JSONField(
        null=True, blank=True,
        help_text="IDs de usuario comparados en la gráfica Historia, en "
                  "orden de selección. null = sin personalizar.",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "membresía de quiniela"
        verbose_name_plural = "membresías de quiniela"
        constraints = [
            UniqueConstraint(
                fields=["user", "quiniela"],
                name="uq_userquiniela_user_quiniela",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.quiniela}"


class Window(models.Model):
    """Ventana de predicción de una quiniela: agrupa 1+ fases del torneo.

    Separa lo que ``Stage`` mezclaba: ``Stage`` queda como estructura del
    torneo (compartida), y ``Window`` lleva el calendario, el peso y la
    presentación **por quiniela**. Agrupa una fase (eliminatorias) o tres
    (grupos concentrados, p. ej. la quiniela original).

    ``name``/``short_name``/``color``/``opens_at``/``send_deadline`` son
    opcionales y, cuando la ventana envuelve **una sola** fase, caen al
    valor de esa fase (ver ``resolved_*``). En ventanas multi-fase el
    fallback es ambiguo, así que deben fijarse explícitos.
    """

    quiniela = models.ForeignKey(
        Quiniela, on_delete=models.CASCADE, related_name="windows")
    stages = models.ManyToManyField(Stage, related_name="windows")
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=50, blank=True)
    short_name = models.CharField(max_length=20, blank=True)
    color = models.CharField(
        max_length=7, blank=True, help_text="Color hex, p. ej. #4CAF50.")
    multiplier = models.DecimalField(
        max_digits=3, decimal_places=1, default=1,
        help_text="Ponderador de la ventana: los puntos se multiplican por "
                  "este factor (1, 1.5, 2 … hasta 10).",
    )
    opens_at = models.DateTimeField(null=True, blank=True)
    send_deadline = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "ventana"
        verbose_name_plural = "ventanas"
        ordering = ["quiniela", "order"]
        constraints = [
            UniqueConstraint(
                fields=["quiniela", "order"],
                name="uq_window_quiniela_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quiniela.slug}:{self.resolved_name()}"

    @property
    def _single_stage(self) -> Stage | None:
        """La fase única si la ventana envuelve exactamente una; si no None.

        Base del fallback de ``resolved_*``: solo una ventana 1:1 tiene una
        fase de la cual heredar nombre/calendario sin ambigüedad.
        """
        stages = list(self.stages.all())
        return stages[0] if len(stages) == 1 else None

    def resolved_name(self) -> str:
        stage = self._single_stage
        return self.name or (stage.name if stage else self.name)

    def resolved_short_name(self) -> str:
        stage = self._single_stage
        return self.short_name or (
            stage.short_name if stage else self.short_name)

    def resolved_color(self) -> str:
        stage = self._single_stage
        return self.color or (stage.color if stage else self.color)

    def resolved_opens_at(self):
        stage = self._single_stage
        return self.opens_at or (stage.opens_at if stage else None)

    def resolved_send_deadline(self):
        stage = self._single_stage
        return self.send_deadline or (
            stage.send_deadline if stage else None)

    @property
    def is_open(self) -> bool:
        """True solo si ya se fijó y alcanzó la apertura (habilitación)."""
        opens_at = self.resolved_opens_at()
        return opens_at is not None and timezone.now() >= opens_at

    @property
    def is_past_deadline(self) -> bool:
        """True si ya venció el plazo de envío."""
        deadline = self.resolved_send_deadline()
        return deadline is not None and timezone.now() >= deadline


class WindowUser(models.Model):
    """Estado de un usuario frente a una ventana de predicción.

    Cuelga de ``Window`` (por quiniela): el ciclo de vida y el envío único
    son por ventana. ``sent_at`` marca cuándo se envió el correo con sus
    pronósticos de la ventana.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="window_states")
    window = models.ForeignKey(
        Window, on_delete=models.PROTECT, related_name="user_states")
    sent_at = models.DateTimeField(null=True, blank=True)

    # Estados del ciclo de vida (derivados, no almacenados).
    UPCOMING = "upcoming"
    EDITING = "editing"
    SENT = "sent"
    LOCKED = "locked"

    class Meta:
        verbose_name = "estado de ventana por usuario"
        verbose_name_plural = "estados de ventana por usuario"
        constraints = [
            UniqueConstraint(
                fields=["user", "window"],
                name="uq_windowuser_user_window",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.window}"

    @property
    def state(self) -> str:
        """Estado actual del usuario en la ventana (ver constantes)."""
        if self.sent_at:
            return self.SENT
        if not self.window.is_open:
            return self.UPCOMING
        if self.window.is_past_deadline:
            return self.LOCKED
        return self.EDITING

    @property
    def can_edit(self) -> bool:
        """Se puede llenar (borrador) mientras la ventana siga viva y sin
        enviar, sin importar ``opens_at``: la apertura solo habilita el
        envío (``can_send``), no el llenado."""
        return self.state in (self.UPCOMING, self.EDITING)

    @property
    def can_send(self) -> bool:
        return self.state == self.EDITING


class Prediction(models.Model):
    """Pronóstico de un usuario para un partido.

    El ciclo de vida (borrador/enviado/confirmado) vive en
    ``WindowUser``, no aquí. Tras conocerse el resultado, la evaluación
    (``services/evaluation.py``) congela aquí los puntos y las reglas
    atinadas para no recalcular al vuelo.
    """

    date = models.DateTimeField()
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="predictions")
    quiniela = models.ForeignKey(
        Quiniela, on_delete=models.CASCADE, related_name="predictions",
        help_text="Quiniela a la que pertenece el pronóstico.",
    )
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="predictions",)
    home_goals = models.IntegerField()
    away_goals = models.IntegerField()
    advancing_team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="predicted_advances",
        null=True,
        blank=True,
        help_text="Solo eliminatorias con empate pronosticado: equipo "
                  "que el jugador cree que gana la tanda de penales y "
                  "avanza.",
    )

    # --- Congelados por la evaluación (services/evaluation.py) ---
    base_points = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Suma de las reglas atinadas, sin ponderar")
    points = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="Puntos finales ya × Window.multiplier")
    rules = models.ManyToManyField(
        Rule, blank=True, related_name="predictions",
        help_text="Reglas atinadas una vez conocido el resultado.")
    evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "match", "quiniela"],
                name="uq_prediction_user_match_quiniela",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.match}"


class ScoreSnapshot(models.Model):
    """Acumulado de puntos de un usuario hasta un partido (tick).

    Existe para cada par (usuario × partido FINISHED) aunque el usuario
    no haya predicho ese partido: el tick avanza igual y su posición
    puede cambiar. Los partidos simultáneos (mismo ``Match.datetime``,
    p. ej. los pares de la jornada 3) comparten ``cumulative_points`` y
    ``position``: el acumulado es por tanda, no por partido individual.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="snapshots")
    quiniela = models.ForeignKey(
        Quiniela, on_delete=models.CASCADE, related_name="snapshots",
        help_text="Quiniela del acumulado.",
    )
    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name="snapshots")
    cumulative_points = models.DecimalField(
        max_digits=5, decimal_places=1, default=0)
    position = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Acumulado por partido"
        verbose_name_plural = "Acumulados por partido"
        ordering = ["match__datetime", "match__of_number"]
        constraints = [
            UniqueConstraint(
                fields=["user", "match", "quiniela"],
                name="uq_snapshot_user_match_quiniela",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.match} · {self.cumulative_points}"
