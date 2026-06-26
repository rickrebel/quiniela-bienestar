"""Reevalúa todos los pronósticos y reconstruye los acumulados.

Útil para backfill (primera carga tras migrar) o tras corregir un
resultado a mano en el admin. En la captura normal de resultados el
recálculo ya corre solo (``views/results.py``).
"""

from django.core.management.base import BaseCommand

from pool.models import Prediction, ScoreSnapshot
from pool.services.evaluation import recompute_all


class Command(BaseCommand):
    help = "Recalcula puntos por pronóstico y acumulados por partido."

    def handle(self, *args, **options) -> None:
        recompute_all()
        evaluated = Prediction.objects.filter(points__isnull=False).count()
        snapshots = ScoreSnapshot.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"{evaluated} pronósticos evaluados, "
            f"{snapshots} acumulados generados."))
