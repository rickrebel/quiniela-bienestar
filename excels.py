from openpyxl import Workbook
from flask_login import current_user

# from views.groups import groups

wb = Workbook()

ws = wb.active
ws.title = "Tus predicciones"

ws.append(
    "Equipo A",
    "Goles A",
    "Goles B",
    "Equipo B",
    "Fecha",
    "Sede"
)

def generate_excel():
    # print(groups)
    print("todo")

