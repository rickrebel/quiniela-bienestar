"""Servicio de generación y envío del Excel de predicciones.

El libro lleva una hoja por fase (las 6): la de grupos abre con una
columna "Grupo"; las de eliminatoria, con "Partido" (el ``of_number``).
Las banderas van como emoji junto al nombre del equipo (en Windows pueden
verse como las siglas del país).
"""

from io import BytesIO

from django.core.mail import EmailMessage
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from pool.views.stages import render_stage_sections
from tournament.models import Stage

XLSX_MIMETYPE = (
    "application/vnd.openxmlformats-officedocument"
    ".spreadsheetml.sheet"
)

# Columnas comunes tras el identificador (Grupo/Partido).
_REST_HEADER = [
    "Local",
    "Goles local",
    "Goles visitante",
    "Visitante",
    "Día",
    "Hora",
    "Sede",
]

# Ancho por columna (caracteres openpyxl), de A a H.
_WIDTHS = [10, 24, 11, 13, 24, 12, 8, 28]

# Columnas a centrar (identificador, goles, día, hora): A, C, D, F, G.
_CENTERED = {"A", "C", "D", "F", "G"}

_FALLBACK_FILL = "D9D9D9"


def _team_cell(team, placeholder: str) -> str:
    """Nombre del equipo con su bandera emoji, o el placeholder textual."""
    if team is None:
        return placeholder
    flag = f"{team.flag_icon} " if team.flag_icon else ""
    return f"{flag}{team.name_es}"


def _header_fill(stage: Stage) -> PatternFill:
    """Relleno del encabezado tomando el color hex de la fase."""
    hex_color = (stage.color or "").lstrip("#")
    if len(hex_color) != 6:
        hex_color = _FALLBACK_FILL
    return PatternFill("solid", fgColor=f"FF{hex_color}")


def _style_sheet(sheet: Worksheet, stage: Stage) -> None:
    """Aplica anchos, encabezado coloreado, centrado y panel fijo."""
    for letter, width in zip("ABCDEFGH", _WIDTHS):
        sheet.column_dimensions[letter].width = width

    bold = Font(bold=True)
    fill = _header_fill(stage)
    center = Alignment(horizontal="center", vertical="center")
    for cell in sheet[1]:
        cell.font = bold
        cell.fill = fill
        cell.alignment = center

    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            if cell.column_letter in _CENTERED:
                cell.alignment = center
    sheet.freeze_panes = "A2"


def _write_sheet(sheet: Worksheet, user, stage: Stage) -> None:
    """Vuelca las predicciones de una fase en su hoja.

    El identificador de cada fila es la letra del grupo (fase de grupos) o
    el ``of_number`` del partido (eliminatoria). El marcador queda en
    blanco si el usuario aún no predijo (o el cruce sigue siendo placeholder).
    """
    is_group = stage.key == Stage.GROUP_STAGE
    sheet.append(["Grupo" if is_group else "Partido", *_REST_HEADER])

    for section in render_stage_sections(user, stage):
        for match in section["matches"]:
            ident = section["key"] if is_group else match.of_number
            sheet.append([
                ident,
                _team_cell(match.home_team, match.home_placeholder),
                getattr(match, "predicted_home", ""),
                getattr(match, "predicted_away", ""),
                _team_cell(match.away_team, match.away_placeholder),
                match.local_day,
                match.local_time,
                match.stadium.name,
            ])
    _style_sheet(sheet, stage)


def generate_excel(user, stage: Stage) -> None:
    """Genera el libro completo de predicciones y lo envía por correo.

    Construye un ``Workbook`` con una hoja por fase. ``stage`` es la fase
    recién enviada y solo alimenta el texto del correo; el archivo refleja
    todo lo predicho hasta ahora. Los títulos de hoja se recortan a 31
    caracteres (límite de openpyxl).
    """
    workbook = Workbook()
    workbook.remove(workbook.active)
    for st in Stage.objects.all():
        sheet = workbook.create_sheet(title=st.short_name[:31])
        _write_sheet(sheet, user, st)

    buffer = BytesIO()
    workbook.save(buffer)

    subject = f"Tus predicciones · {stage.name}"
    body = (
        f"Acabas de enviar tus predicciones de {stage.name}. Te adjunto "
        "el Excel con tu quiniela completa hasta ahora. Saludos!"
    )
    message = EmailMessage(subject=subject, body=body, to=[user.email])
    message.attach("predicciones.xlsx", buffer.getvalue(), XLSX_MIMETYPE)
    message.send()
