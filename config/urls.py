"""Root URL configuration for the config project.

La app cuelga de un prefijo ``/<slug>/`` (la quiniela activa); auth queda
global y el dominio pelón redirige a la ventana 1 de la quiniela del
dominio/usuario.
"""
from django.contrib import admin
from django.urls import include, path

from pool.views.scope import legacy_redirect, root_redirect

# Compatibilidad: rutas planas previas (en marcadores/caché) → su
# equivalente bajo el prefijo de quiniela. Van antes del include de slug
# para que ``stage/…`` no se interprete como una quiniela inexistente.
legacy_patterns = [
    path("stage/grupos/", legacy_redirect("window", order=1)),
    path("stage/<str:key>/", legacy_redirect("by_date")),
    path("posiciones/", legacy_redirect("standings")),
    path("calendario/", legacy_redirect("by_date")),
    path("reglas/", legacy_redirect("reglas")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("pool.urls_auth")),
    *legacy_patterns,
    path("<slug:quiniela>/", include("pool.urls")),
    path("", root_redirect, name="root"),
]
