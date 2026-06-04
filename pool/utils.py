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


def convert_date(date: datetime) -> str:
    """Formatea una fecha como '{día} de {mes}, {HH:MM}'.

    El mes se devuelve en español (enero..diciembre). La hora se
    formatea en 24 horas con ceros a la izquierda.
    """
    month = MONTHS_ES[date.month]
    return f"{date.day} de {month}, {date.strftime('%H:%M')}"
