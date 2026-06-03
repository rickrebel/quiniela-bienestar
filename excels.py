from openpyxl import Workbook
from flask_login import current_user

from db.models import Match, Prediction
from views.groups import renderMatchesByGroup

from email.message import EmailMessage
from io import BytesIO
from dotenv import load_dotenv
import smtplib
import os

load_dotenv()

EMAIL = os.environ.get("GMAIL_USER")
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
MAIL_SERVER = os.environ.get("SMTP_SERVER")
MAIL_PORT = os.environ.get("SMTP_PORT")

wb = Workbook()

default_sheet = wb.active
wb.remove(default_sheet)


def generate_excel():
    groups = renderMatchesByGroup(Match, Prediction, current_user)

    for group_name, matches in groups.items():
        ws = wb.create_sheet(title=f"Grupo {group_name}")
        ws.append([
            "Equipo A",
            "Goles A",
            "Goles B",
            "Equipo B",
            "Fecha",
            "Sede"
        ])

        for match in matches:
            predicted_a = getattr(match, "predicted_a", 0)
            predicted_b = getattr(match, "predicted_b", 0)
            ws.append([
                match.team_a.name,
                predicted_a,
                predicted_b,
                match.team_b.name,
                match.formatted_date,
                match.stadium
            ])

    buffer = BytesIO()
    wb.save(buffer)

    msg = EmailMessage()
    msg["Subject"] = "Tus predicciones"
    msg["From"] = EMAIL
    msg["To"] = current_user.email
    msg.set_content("Te adjunto el excel de tus predicciones de la fase de grupos. Saludos!")

    msg.add_attachment(
        buffer.getvalue(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="predicciones.xlsx"
    )

    with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT) as smtp:
        # smtp.set_debuglevel(1)
        smtp.login(EMAIL, APP_PASSWORD)
        smtp.send_message(msg)



