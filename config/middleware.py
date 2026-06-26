"""Middleware del proyecto."""

from django.utils.cache import add_never_cache_headers


class NoCacheHTMLMiddleware:
    """Evita que el navegador sirva HTML cacheado tras un deploy.

    Las páginas server-rendered salían sin cabeceras de cache, así que un
    navegador podía conservar una versión vieja apuntando a un bundle JS de
    hash anterior (el JS no se refrescaba hasta una recarga forzada). Aquí
    marcamos solo el HTML como no cacheable; los assets estáticos están
    hasheados y los sirve nginx con su propia cache larga, así que no pasan
    por aquí y no se ven afectados.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get("Content-Type", "").startswith("text/html"):
            add_never_cache_headers(response)
        return response
