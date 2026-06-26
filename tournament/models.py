"""Modelos de datos deportivos del torneo (estructura y resultados).

Fuentes de datos:
- OF = openfootball (github.com/openfootball/worldcup.json): seed inicial
  (estructura, estadios, banderas, grupos). Se consulta una sola vez.
- FD = football-data.org (API v4): resultados a lo largo del torneo.

Convención: ``home``/``away`` en lugar de ``a``/``b`` para alinear con FD.
"""

from django.db import models
from django.utils import timezone


class Stadium(models.Model):
    """Sede del torneo. Todos los campos provienen de OF (stadiums)."""

    COUNTRY_CHOICES = [
        ("us", "Estados Unidos"),
        ("ca", "Canadá"),
        ("mx", "México"),
    ]

    name = models.CharField(max_length=100, unique=True)
    name_es = models.CharField(
        max_length=100, help_text="Nombre para mostrar, en español.",
        blank=True, null=True)
    city = models.CharField(max_length=100, unique=True)
    country = models.CharField(max_length=2, choices=COUNTRY_CHOICES)
    utc_offset = models.SmallIntegerField(
        help_text="Offset UTC del estadio durante el torneo (p. ej. -6).")
    capacity = models.PositiveIntegerField(null=True, blank=True)
    coords = models.CharField(
        max_length=50, blank=True,
        help_text="Coordenadas crudas de OF, en grados (string).",)

    class Meta:
        verbose_name = "estadio"
        verbose_name_plural = "estadios"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def flag_path(self) -> str:
        """Ruta estática de la mini-bandera (20px) del país de la sede."""
        return f"flags_20/{self.country}.webp" if self.country else ""


class Stage(models.Model):
    """Fase del torneo, alineada a las claves de stage de FD.

    Son 6 fases (las que el usuario predice, una por chip de la UI). La
    fase ``FINAL`` agrupa el partido por el tercer lugar y la final; se
    distinguen por ``Match.of_number`` (103 = tercer lugar, 104 = final).
    """
    LAST_32 = "LAST_32"
    LAST_16 = "LAST_16"
    QUARTER_FINALS = "QUARTER_FINALS"
    SEMI_FINALS = "SEMI_FINALS"
    FINAL = "FINAL"
    key = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=20)
    color = models.CharField(
        max_length=7, blank=True, help_text="Color hex, p. ej. #4CAF50."
    )
    order = models.PositiveSmallIntegerField(unique=True)
    is_group = models.BooleanField(
        default=False,
        help_text="True en las 3 jornadas de grupos; la UI las colapsa "
                  "en una sola pestaña.",
    )
    opens_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Apertura de predicciones (UTC). Antes: inputs off.",
    )
    send_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Límite para enviar (UTC). Al vencer: auto-envía lo "
                  "guardado.",
    )

    class Meta:
        verbose_name = "fase"
        verbose_name_plural = "fases"
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_open(self) -> bool:
        """True solo si ya se fijó y alcanzó la apertura (habilitación).

        ``opens_at`` nulo = fase aún no habilitada: se ve pero no se edita
        hasta que el admin fije la fecha de apertura.
        """
        return self.opens_at is not None and timezone.now() >= self.opens_at

    @property
    def is_past_deadline(self) -> bool:
        """True si ya venció el plazo de envío."""
        return (
            self.send_deadline is not None
            and timezone.now() >= self.send_deadline
        )


class Team(models.Model):
    """Selección nacional. Combina datos de OF (base) y FD (enriquecido).

    El join OF↔FD se hace por ``fifa_code`` (OF) == ``tla`` (FD). Los
    campos FD se llenan con ``load_teams --enrich-fd`` cuando hay token.
    """

    GROUP_CHOICES = [(c, c) for c in "ABCDEFGHIJKL"]
    CONFED_CHOICES = [
        ("UEFA", "UEFA"),
        ("CONMEBOL", "CONMEBOL"),
        ("CONCACAF", "CONCACAF"),
        ("CAF", "África"),
        ("AFC", "Asía"),
        ("OFC", "Oceanía"),
    ]

    # --- OF (seed inicial) ---
    name = models.CharField(max_length=100, unique=True)
    name_es = models.CharField(
        max_length=100, help_text="Nombre corto para mostrar, en español."
    )
    fifa_code = models.CharField(max_length=3, unique=True)
    flag_icon = models.CharField(
        max_length=16, blank=True, help_text="Bandera como emoji."
    )
    flag_unicode = models.CharField(max_length=120, blank=True)
    flag_code = models.CharField(
        max_length=6, blank=True,
        help_text="ISO alpha-2 del PNG local (ej. 'mx'; 'gb-eng' para ENG)."
    )
    group_name = models.CharField(max_length=1, choices=GROUP_CHOICES)
    confederation = models.CharField(max_length=10, choices=CONFED_CHOICES)

    # --- FD (enriquecido) ---
    fd_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    short_name = models.CharField(max_length=50, blank=True)
    crest = models.URLField(blank=True, help_text="URL del escudo (FD).")

    # --- Crudos por fuente, para explotar a futuro ---
    raw_of = models.JSONField(default=dict, blank=True)
    raw_fd = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "selección"
        verbose_name_plural = "selecciones"
        ordering = ["group_name", "name_es"]

    def __str__(self) -> str:
        return self.name_es or self.name

    @property
    def flag_path(self) -> str:
        """Ruta estática del PNG de bandera (vacía si no hay código)."""
        return f"flags_40/{self.flag_code}.png" if self.flag_code else ""


class Match(models.Model):
    """Partido del torneo. Estructura de OF; resultados de FD.

    ``home_team``/``away_team`` son nulos en eliminatorias hasta que se
    define el cruce; mientras tanto ``home_placeholder``/``away_placeholder``
    guardan el texto de OF (p. ej. "2A", "W74", "3A/B/C/D/F").
    """

    # of_number de los partidos decisivos (hardcode acordado).
    THIRD_PLACE_NUMBER = 103
    FINAL_NUMBER = 104

    STATUS_CHOICES = [
        ("SCHEDULED", "Programado"),
        ("TIMED", "Con hora"),
        ("IN_PLAY", "En juego"),
        ("PAUSED", "Pausado"),
        ("FINISHED", "Finalizado"),
        ("SUSPENDED", "Suspendido"),
        ("POSTPONED", "Pospuesto"),
        ("CANCELLED", "Cancelado"),
        ("AWARDED", "Adjudicado"),
    ]

    REGULAR = "REGULAR"
    EXTRA_TIME = "EXTRA_TIME"
    PENALTY_SHOOTOUT = "PENALTY_SHOOTOUT"
    DECIDED_BY_CHOICES = [
        (REGULAR, "Tiempo regular"),
        (EXTRA_TIME, "Tiempo extra"),
        (PENALTY_SHOOTOUT, "Penales"),
    ]

    datetime = models.DateTimeField(
        help_text="Fecha y hora del partido en UTC."
    )
    stage = models.ForeignKey(
        Stage, on_delete=models.PROTECT, related_name="matches"
    )
    stadium = models.ForeignKey(
        Stadium, on_delete=models.PROTECT, related_name="matches"
    )
    home_team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="home_matches",
        null=True,
        blank=True,
    )
    away_team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="away_matches",
        null=True,
        blank=True,
    )
    home_placeholder = models.CharField(
        max_length=20, blank=True,
        help_text='Origen textual del equipo local (p. ej. "2A", "W74").',)
    away_placeholder = models.CharField(
        max_length=20, blank=True,
        help_text='Origen textual del equipo visitante (p. ej. "1B", "W75").')

    # Etiqueta legible del partido en eliminatoria (vacía en grupos). El
    # identificador numérico es ``of_number``; el cruce se traza por él.
    name = models.CharField(
        max_length=40, blank=True,
        help_text='Etiqueta legible (p. ej. "Cuartos 3", "Final").')

    home_goals = models.PositiveSmallIntegerField(null=True, blank=True)
    away_goals = models.PositiveSmallIntegerField(null=True, blank=True)

    decided_by = models.CharField(
        max_length=20, choices=DECIDED_BY_CHOICES, blank=True)
    home_penalties = models.PositiveSmallIntegerField(null=True, blank=True)
    away_penalties = models.PositiveSmallIntegerField(null=True, blank=True)

    home_yellow = models.PositiveSmallIntegerField(null=True, blank=True)
    away_yellow = models.PositiveSmallIntegerField(null=True, blank=True)
    home_red = models.PositiveSmallIntegerField(null=True, blank=True)
    away_red = models.PositiveSmallIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="SCHEDULED"
    )
    of_number = models.PositiveSmallIntegerField(
        unique=True, help_text="Número de partido 1..104 (73..104 = OF num)."
    )
    fd_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    raw_fd = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "partido"
        verbose_name_plural = "partidos"
        ordering = ["of_number"]

    def __str__(self) -> str:
        home = self.home_team or self.home_placeholder
        away = self.away_team or self.away_placeholder
        return f"#{self.of_number} {home} vs {away}"

    @property
    def is_final(self) -> bool:
        return self.of_number == self.FINAL_NUMBER

    @property
    def is_third_place(self) -> bool:
        return self.of_number == self.THIRD_PLACE_NUMBER
