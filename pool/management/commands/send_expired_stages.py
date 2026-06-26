"""Auto-envía las ventanas cuyo plazo venció con lo que el usuario guardó.

Por cada WindowUser sin ``sent_at`` cuya ventana ya pasó su
``resolved_send_deadline``: si tiene predicciones guardadas en esa
quiniela, marca ``sent_at`` y manda el Excel. Si no guardó nada, se omite.

El plazo es ``resolved_send_deadline`` (override de ventana o fallback de
fase), que no es un campo de BD: se filtra en Python sobre el pendiente.

PENDIENTE: programar como cron en EC2 (ver docs/design-models/decisiones.md).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from pool.models import Prediction, WindowUser
from pool.services.excel import generate_excel


class Command(BaseCommand):
    help = "Auto-envía las ventanas vencidas con lo guardado por el usuario."

    def handle(self, *args, **options) -> None:
        now = timezone.now()
        pending = WindowUser.objects.select_related(
            "window__quiniela", "user"
        ).prefetch_related("window__stages").filter(
            sent_at__isnull=True,
        ).exclude(user__is_virtual=True)

        count = 0
        for wu in pending:
            window = wu.window
            deadline = window.resolved_send_deadline()
            if deadline is None or deadline > now:
                continue
            has_preds = Prediction.objects.filter(
                user=wu.user, quiniela_id=window.quiniela_id,
                match__stage__in=window.stages.all(),
            ).exists()
            if not has_preds:
                continue
            wu.sent_at = now
            wu.save(update_fields=["sent_at"])
            generate_excel(wu.user, window, window.quiniela)
            count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Ventanas auto-enviadas: {count}."
        ))
