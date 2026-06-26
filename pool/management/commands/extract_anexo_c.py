"""Extrae el anexo C (combinaciones de los 8 mejores terceros) a JSON.

Lee la única tabla de ``docs/anexo_c.html`` (HTML de Wikipedia con celdas
combinadas), expande los ``rowspan``/``colspan`` a una grilla rectangular y
escribe ``pool/services/data/anexo_c.json``. Sin base de datos: es un paso
de preprocesamiento reproducible e idempotente.

Cada una de las 495 filas asocia el conjunto de 8 grupos que aportaron un
tercero clasificado con la asignación de cada tercero al rival que lo
enfrenta en dieciseisavos (slots ganadores A, B, D, E, G, I, K, L).
"""

import json
from pathlib import Path

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Orden fijo de los 8 slots ganadores, tomado del encabezado de la tabla
# ("1A vs", "1B vs", …). Es invariante del torneo, no se infiere por fila.
WINNER_SLOTS = ["A", "B", "D", "E", "G", "I", "K", "L"]

EXPECTED_ROWS = 495
EXPECTED_COLS = 22  # 1 número + 12 grupos + 1 separador + 8 slots
GROUP_COLS = range(1, 13)  # cols 1..12 → grupos A..L
SLOT_COLS = range(14, 22)  # cols 14..21 → terceros asignados

HTML_PATH = Path("docs/anexo_c.html")
JSON_PATH = Path("pool/services/data/anexo_c.json")


class Command(BaseCommand):
    """Convierte la tabla del anexo C en ``anexo_c.json`` reproducible."""

    help = (
        "Extrae las 495 combinaciones de los 8 mejores terceros desde "
        "docs/anexo_c.html y las escribe en pool/services/data/anexo_c.json."
    )

    def handle(self, *args, **options) -> None:
        base = Path(settings.BASE_DIR)
        html_file = base / HTML_PATH
        if not html_file.exists():
            raise CommandError(f"No existe el HTML: {html_file}")

        grid = self._build_grid(html_file)
        combinations = self._parse_rows(grid)

        out_file = base / JSON_PATH
        out_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "winner_slots": WINNER_SLOTS,
            "combinations": combinations,
        }
        with out_file.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
            fh.write("\n")

        self.stdout.write(self.style.SUCCESS(
            f"Escritas {len(combinations)} combinaciones en {out_file}."))

    def _build_grid(self, html_file: Path) -> list[list[str]]:
        """Expande la tabla a una grilla rectangular sin celdas combinadas.

        Recorre filas y, por cada una, va colocando el texto de cada ``td``
        en la siguiente columna libre, respetando los ``rowspan`` que aún
        proyectan valor desde filas anteriores. Un ``colspan`` repite el
        texto en columnas contiguas; un ``rowspan`` agenda ese texto para
        las filas siguientes mediante ``pending`` (celdas pendientes por
        columna, con cuántas filas más ocupan).
        """
        soup = BeautifulSoup(html_file.read_text(encoding="utf-8"),
                             "html.parser")
        table = soup.find("table")
        if table is None:
            raise CommandError("No se encontró ninguna <table> en el HTML.")

        grid: list[list[str]] = []
        # pending[col] = [texto, filas_restantes] proyectado por un rowspan.
        pending: dict[int, list] = {}

        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue

            row: list[str] = []
            col = 0
            cell_iter = iter(cells)
            current = next(cell_iter, None)

            while True:
                # Primero vuelca cualquier rowspan vivo en esta columna.
                if col in pending:
                    text, left = pending[col]
                    row.append(text)
                    left -= 1
                    if left:
                        pending[col] = [text, left]
                    else:
                        del pending[col]
                    col += 1
                    continue

                if current is None:
                    break

                text = current.get_text(strip=True)
                colspan = int(current.get("colspan", 1))
                rowspan = int(current.get("rowspan", 1))
                for _ in range(colspan):
                    row.append(text)
                    if rowspan > 1:
                        pending[col] = [text, rowspan - 1]
                    col += 1
                current = next(cell_iter, None)

            grid.append(row)

        return grid

    def _parse_rows(self, grid: list[list[str]]) -> dict:
        """Valida la grilla y construye el dict de combinaciones."""
        if not grid:
            raise CommandError("La tabla está vacía.")

        # La primera fila es el encabezado; el resto son datos.
        data_rows = grid[1:]
        if len(data_rows) != EXPECTED_ROWS:
            raise CommandError(
                f"Se esperaban {EXPECTED_ROWS} filas de datos, "
                f"se encontraron {len(data_rows)}.")

        combinations: dict[str, dict] = {}
        for idx, row in enumerate(data_rows, start=1):
            if len(row) != EXPECTED_COLS:
                raise CommandError(
                    f"Fila {idx}: se esperaban {EXPECTED_COLS} columnas, "
                    f"hay {len(row)}.")

            qualified = [row[c] for c in GROUP_COLS if row[c]]
            if len(qualified) != 8:
                raise CommandError(
                    f"Fila {idx}: se esperaban 8 grupos clasificados, "
                    f"hay {len(qualified)} ({qualified}).")
            qualified_set = set(qualified)

            assignment: dict[str, str] = {}
            for slot, col in zip(WINNER_SLOTS, SLOT_COLS):
                raw = row[col]
                if not raw:
                    raise CommandError(
                        f"Fila {idx}: slot {slot} sin asignación.")
                third = raw.removeprefix("3")
                if third not in qualified_set:
                    raise CommandError(
                        f"Fila {idx}: el tercero '{third}' (slot {slot}) no "
                        f"está entre los grupos clasificados {qualified_set}.")
                assignment[slot] = third

            key = "".join(sorted(qualified))
            if key in combinations:
                raise CommandError(
                    f"Fila {idx}: clave duplicada '{key}'.")
            combinations[key] = assignment

        if len(combinations) != EXPECTED_ROWS:
            raise CommandError(
                f"Se esperaban {EXPECTED_ROWS} claves únicas, "
                f"hay {len(combinations)}.")

        return combinations
