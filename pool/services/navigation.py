"""Navegación: ¿a qué ventana mandar a un usuario que entra "a la quiniela"?

La raíz de cada quiniela (y el dominio pelón / post-login) debe aterrizar en
la fase que se está jugando hoy. Como cada quiniela ordena sus ventanas
distinto (sanginiela concentra los grupos en una ventana, bienestar los parte
en 3), el ``order`` destino no es fijo: se deriva de las fechas de los
partidos. Helpers puros (sin estado de usuario), aislados aquí porque los
consume ``views/scope.py``, que no puede importar de ``views/stages.py`` sin
import circular.
"""

from datetime import timedelta

from django.utils import timezone

from pool.models import Quiniela, Window
from tournament.models import Match


def current_window(quiniela: Quiniela) -> Window | None:
    """Ventana de la quiniela que se está jugando ahora.

    Determinística por fecha (no depende de resultados capturados): toma el
    partido **más temprano aún no concluido** (kickoff >= ahora − 3 h, que
    cubre 90'+alargue/penales) entre las fases de la quiniela y devuelve la
    ventana que lo contiene. Antes del torneo cae en la primera ventana; con
    todo concluido, en la última. En días de descanso entre rondas no hay
    partido hoy pero el no concluido más temprano sigue dando la ronda
    vigente, sin casos especiales.
    """
    windows = list(
        quiniela.windows.prefetch_related("stages").order_by("order")
    )
    if not windows:
        return None
    stage_to_window = {s.id: w for w in windows for s in w.stages.all()}
    cutoff = timezone.now() - timedelta(hours=3)
    stage_id = (
        Match.objects
        .filter(stage_id__in=stage_to_window, datetime__gte=cutoff)
        .order_by("datetime")
        .values_list("stage_id", flat=True)
        .first()
    )
    if stage_id is not None:
        return stage_to_window[stage_id]
    return windows[-1]


def window_route(window: Window | None) -> tuple[str, dict] | None:
    """``(nombre_url, kwargs)`` para redirigir a una ventana.

    Las ventanas de grupo no se entran por ``order`` (``window_view`` las
    reenvía): su ruta canónica es el tab único ``groups``. Réplica la regla
    de ``stages._is_group_window``.
    """
    if window is None:
        return None
    stages = list(window.stages.all())
    if stages and all(s.is_group for s in stages):
        return "groups", {"quiniela": window.quiniela.slug}
    return "window", {"quiniela": window.quiniela.slug, "order": window.order}
