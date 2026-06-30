"""Resolución de la quiniela activa por path y por dominio.

El routing monta la app bajo ``/<slug>/`` (ver ``config/urls.py``). El
decorador ``with_quiniela`` resuelve ese slug a la instancia y la cuelga en
``request.quiniela`` para vistas y context processors. La auto-detección por
dominio define a qué quiniela manda el dominio pelón y el post-login.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from pool.models import Quiniela
from pool.services.membership import active_quiniela
from pool.services.navigation import current_window, window_route


def with_quiniela(view):
    """Fija ``request.quiniela`` desde el slug del path y lo consume.

    El prefijo ``/<slug>/`` inyecta ``quiniela`` como kwarg de la vista; el
    decorador lo resuelve (404 si no existe), lo cuelga del request y lo
    quita de los kwargs para que la firma de la vista quede limpia. Va por
    dentro de ``login_required`` (primero autenticar, luego resolver).
    """
    @wraps(view)
    def wrapper(request: HttpRequest, quiniela: str, *args, **kwargs):
        obj = Quiniela.objects.filter(slug=quiniela).first()
        if obj is None:
            raise Http404("Quiniela inexistente")
        request.quiniela = obj
        return view(request, *args, **kwargs)

    return wrapper


def quiniela_for_host(host: str) -> str | None:
    """Slug de la quiniela según el dominio (auto-detección).

    ``QUINIELA_DOMAINS`` mapea host→slug; sin coincidencia cae a
    ``DEFAULT_QUINIELA_SLUG`` y, si tampoco, a la primera quiniela de la BD
    (para que el local sin configurar igual resuelva).
    """
    host = (host or "").split(":")[0]
    slug = settings.QUINIELA_DOMAINS.get(host) or settings.DEFAULT_QUINIELA_SLUG
    if slug:
        return slug
    return Quiniela.objects.values_list("slug", flat=True).first()


def home_slug(request: HttpRequest) -> str | None:
    """Slug a donde mandar al usuario: su quiniela activa o la del dominio."""
    if request.user.is_authenticated:
        quiniela = active_quiniela(request.user)
        if quiniela is not None:
            return quiniela.slug
    return quiniela_for_host(request.get_host())


def _current_window_redirect(slug: str | None) -> HttpResponse:
    """Redirige al destino de ``slug``: su ventana vigente (la fase de hoy).

    Centraliza la decisión a partir de un slug (raíz con slug, dominio pelón
    y post-login la comparten). Sin slug resoluble o quiniela sin ventanas,
    cae a login.
    """
    if slug is None:
        return redirect("login")
    quiniela = Quiniela.objects.filter(slug=slug).first()
    route = window_route(current_window(quiniela)) if quiniela else None
    if route is None:
        return redirect("login")
    name, kwargs = route
    return redirect(name, **kwargs)


@login_required
def quiniela_root(request: HttpRequest, quiniela: str) -> HttpResponse:
    """Raíz de la quiniela (``/<slug>/``) → ventana vigente (la fase de hoy).

    El slug llega como kwarg ``quiniela`` desde el include de ``pool.urls``
    (ya es el string), así que no necesita ``with_quiniela``.
    """
    return _current_window_redirect(quiniela)


def root_redirect(request: HttpRequest) -> HttpResponse:
    """Dominio pelón → ventana vigente de la quiniela del usuario/dominio."""
    return _current_window_redirect(home_slug(request))


def post_auth_redirect(
    request: HttpRequest, slug: str | None = None
) -> HttpResponse:
    """Destino tras login/registro/reset: ``next`` seguro o la quiniela.

    Si la petición trae un ``next`` (de un enlace protegido) que apunta al
    mismo host, manda ahí. Si no, usa ``slug`` (cuando el llamador sabe a
    qué quiniela acaba de inscribir) o ``home_slug`` (primera membresía).
    Sin slug resoluble (p. ej. superusuario sin membresía) cae a login.
    """
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, {request.get_host()}, request.is_secure()
    ):
        return redirect(nxt)
    return _current_window_redirect(slug or home_slug(request))


def legacy_redirect(to_name: str, **extra):
    """Vista que reenvía una ruta vieja (plana) a su equivalente bajo slug.

    Los marcadores y la caché del navegador apuntan a las rutas previas sin
    prefijo de quiniela (``/posiciones/``, ``/stage/grupos/``…). Estas
    vistas resuelven la quiniela del usuario/dominio y redirigen al nombre
    nuevo. Los kwargs viejos de la ruta (p. ej. la ``key`` de fase) se
    descartan: no tienen equivalente; las fases sueltas caen al calendario
    (``by_date``). Los kwargs nuevos van en ``extra`` (p. ej. ``order=1``).
    """
    def view(request: HttpRequest, **kwargs) -> HttpResponse:
        slug = home_slug(request)
        if slug is None:
            return redirect("login")
        return redirect(to_name, quiniela=slug, **extra)

    return view
