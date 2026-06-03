# esto sólo existe porque los dates del json de matches son inconsistentes,
# tendría que arreglarse el json
# para que esto funcione hay que permitir temporalmente strings en el date del modelo Match

from quiniela import app, db
from db.models import Match
from datetime import datetime

with app.app_context():
    matches = Match.query.all()

    def parse_fecha(fecha_str):
        """
        Convierte diferentes formatos posibles a datetime.
        """
        formatos = [
            "%Y-%m-%d, %H:%M",  # con coma
            "%Y-%m-%d %H:%M",   # sin coma
            "%Y-%m-%dT%H:%M",   # ISO corto
            "%Y-%m-%dT%H:%M:%S" # ISO completo
        ]

        for fmt in formatos:
            try:
                return datetime.strptime(fecha_str, fmt)
            except ValueError:
                pass

        raise ValueError(f"Formato de fecha no reconocido: {fecha_str}")

    for match in matches:
        if isinstance(match.date, str):
            try:
                match.date = parse_fecha(match.date)
            except ValueError as e:
                print(f"Error en match {match.id}: {e}")

    db.session.commit()