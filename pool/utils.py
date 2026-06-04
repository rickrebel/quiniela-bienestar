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


def format_day(date: datetime) -> str:
    """Formatea la fecha como '{día} de {mes}' (mes en español)."""
    return f"{date.day} de {MONTHS_ES[date.month]}"


def format_time(date: datetime) -> str:
    """Formatea la hora en 24 h con ceros a la izquierda ('HH:MM')."""
    return date.strftime("%H:%M")
