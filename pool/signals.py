"""Señales de la app pool."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from tournament.models import Stage

from .models import StageUser, User


@receiver(post_save, sender=User)
def create_stage_users(
    sender: type, instance: User, created: bool, **kwargs
) -> None:
    """Materializa un StageUser por cada fase al dar de alta un usuario.

    ``ignore_conflicts`` respeta el UniqueConstraint (user, stage) por si
    la señal se redispara; solo crea las filas que falten. ``raw`` evita
    duplicar contra los StageUser que un ``loaddata`` trae en el fixture.
    """
    if kwargs.get("raw") or not created:
        return
    StageUser.objects.bulk_create(
        [StageUser(user=instance, stage=s) for s in Stage.objects.all()],
        ignore_conflicts=True,
    )
