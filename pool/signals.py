"""Señales de la app pool."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserQuiniela, WindowUser


@receiver(post_save, sender=UserQuiniela)
def create_window_users(
    sender: type, instance: UserQuiniela, created: bool, **kwargs
) -> None:
    """Materializa un WindowUser por cada ventana al inscribir a un usuario.

    El estado por ventana cuelga de la membresía, no del alta del usuario:
    una persona en dos quinielas tiene los WindowUser de ambas. Idempotente
    (``ignore_conflicts`` sobre el UniqueConstraint (user, window)); ``raw``
    evita duplicar contra los que trae un ``loaddata``.
    """
    if kwargs.get("raw") or not created:
        return
    WindowUser.objects.bulk_create(
        [
            WindowUser(user=instance.user, window=w)
            for w in instance.quiniela.windows.all()
        ],
        ignore_conflicts=True,
    )
