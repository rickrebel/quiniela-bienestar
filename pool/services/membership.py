"""Resolución de la quiniela activa de un usuario (interina, Subtarea 3).

Stand-in hasta que la Subtarea 4 resuelva la quiniela por path/dominio
(``request.quiniela``). Hoy cada usuario real pertenece a una sola
quiniela, así que su primera membresía es inequívoca.
"""

from pool.models import Quiniela, User, UserQuiniela


def active_quiniela(user: User) -> Quiniela | None:
    """Quiniela activa del usuario: su primera membresía por antigüedad.

    Devuelve ``None`` si no tiene alta en ninguna (p. ej. un superusuario
    que entra al admin); los llamadores degradan a un board vacío.
    """
    membership = (
        UserQuiniela.objects.filter(user=user)
        .select_related("quiniela")
        .order_by("joined_at")
        .first()
    )
    return membership.quiniela if membership else None
