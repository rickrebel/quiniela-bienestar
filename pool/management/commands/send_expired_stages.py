"""Auto-envía las fases cuyo plazo venció con lo que el usuario guardó.

Por cada StageUser sin ``sent_at`` cuya fase ya pasó su ``send_deadline``:
si tiene predicciones guardadas, marca ``sent_at`` y manda el Excel. Si no
guardó nada, se omite (no hay qué enviar).

PENDIENTE: programar como cron en EC2 (ver docs/design-models/decisiones.md).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from pool.models import Prediction, StageUser
from pool.services.excel import generate_excel


class Command(BaseCommand):
    help = "Auto-envía las fases vencidas con lo guardado por el usuario."

    def handle(self, *args, **options) -> None:
        now = timezone.now()
        pending = StageUser.objects.select_related("stage", "user").filter(
            sent_at__isnull=True,
            stage__send_deadline__isnull=False,
            stage__send_deadline__lte=now,
        ).exclude(user__is_virtual=True)

        count = 0
        for stage_user in pending:
            has_preds = Prediction.objects.filter(
                user=stage_user.user, match__stage=stage_user.stage
            ).exists()
            if not has_preds:
                continue
            stage_user.sent_at = now
            stage_user.save(update_fields=["sent_at"])
            generate_excel(stage_user.user, stage_user.stage)
            count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Fases auto-enviadas: {count}."
        ))
