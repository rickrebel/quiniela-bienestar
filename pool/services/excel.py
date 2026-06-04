"""Servicio de generación y envío del Excel de predicciones por fase."""

from io import BytesIO

from django.core.mail import EmailMessage
from openpyxl import Workbook

from pool.views.stages import render_stage_matches
from tournament.models import Stage

XLSX_MIMETYPE = (
    "application/vnd.openxmlformats-officedocument"
    ".spreadsheetml.sheet"
)

HEADER_ROW = [
    "Local",
    "Goles local",
    "Goles visitante",
    "Visitante",
    "Fecha",
    "Sede",
]


def _team_name(team, placeholder: str) -> str:
    """Nombre corto del equipo, o su placeholder si aún no se define."""
    return team.name_es if team is not None else placeholder


def generate_excel(user, stage: Stage) -> None:
    """Genera el Excel de una fase y lo envía por correo al usuario.

    Construye un ``Workbook`` local por llamada. En fase de grupos crea
    una hoja por grupo; en eliminatoria, una sola hoja con la fase. Los
    títulos de hoja se recortan a 31 caracteres (límite de openpyxl).
    """
    workbook = Workbook()
    workbook.remove(workbook.active)

    grouped = render_stage_matches(user, stage)
    for group_name, matches in grouped.items():
        title = f"Grupo {group_name}" if group_name else stage.short_name
        sheet = workbook.create_sheet(title=title[:31])
        sheet.append(HEADER_ROW)
        for match in matches:
            datetime = match.datetime.date()
            sheet.append([
                _team_name(match.home_team, match.home_placeholder),
                getattr(match, "predicted_home", 0),
                getattr(match, "predicted_away", 0),
                _team_name(match.away_team, match.away_placeholder),
                datetime,
                match.stadium.name,
            ])

    buffer = BytesIO()
    workbook.save(buffer)

    subject = f"Tus predicciones · {stage.name}"
    body = (
        f"Te adjunto el Excel de tus predicciones de {stage.name}. "
        "Saludos!"
    )
    message = EmailMessage(subject=subject, body=body, to=[user.email])
    message.attach("predicciones.xlsx", buffer.getvalue(), XLSX_MIMETYPE)
    message.send()
