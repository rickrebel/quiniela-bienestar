"""Funciones auxiliares de presentación para la quiniela."""

from datetime import datetime

MONTHS_ES: dict[int, str] = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

# date.weekday(): 0 = lunes … 6 = domingo.
WEEKDAYS_ES: dict[int, str] = {
    0: "lunes",
    1: "martes",
    2: "miércoles",
    3: "jueves",
    4: "viernes",
    5: "sábado",
    6: "domingo",
}


def format_day(date: datetime) -> str:
    """Formatea la fecha como '{día} de {mes}' (mes en español)."""
    return f"{date.day} de {MONTHS_ES[date.month]}"


def format_long_day(date: datetime) -> str:
    """Formatea como '{día semana} {día} de {mes}' ('lunes 15 de junio')."""
    return f"{WEEKDAYS_ES[date.weekday()]} {format_day(date)}"


def format_time(date: datetime) -> str:
    """Formatea la hora en 24 h con ceros a la izquierda ('HH:MM')."""
    return date.strftime("%H:%M")
