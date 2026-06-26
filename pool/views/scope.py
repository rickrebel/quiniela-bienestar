"""Resolución de la quiniela activa por path y por dominio.

El routing monta la app bajo ``/<slug>/`` (ver ``config/urls.py``). El
decorador ``with_quiniela`` resuelve ese slug a la instancia y la cuelga en
``request.quiniela`` para vistas y context processors. La auto-detección por
dominio define a qué quiniela manda el dominio pelón y el post-login.
"""

from functools import wraps

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect

from pool.models import Quiniela
from pool.services.membership import active_quiniela


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


def root_redirect(request: HttpRequest) -> HttpResponse:
    """Dominio pelón → ventana 1 de la quiniela del usuario o del dominio."""
    slug = home_slug(request)
    if slug is None:
        return redirect("login")
    return redirect("window", quiniela=slug, order=1)


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
