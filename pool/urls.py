"""Rutas de la app pool (quiniela)."""

from django.urls import path
from django.views.generic import RedirectView

from pool.views import auth, groups, predictions

urlpatterns = [
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    path("grupos/", groups.grupos, name="grupos"),
    path(
        "save_predictions/",
        predictions.save_predictions,
        name="save_predictions",
    ),
    path(
        "submit_predictions/",
        predictions.submit_predictions,
        name="submit_predictions",
    ),
    path(
        "",
        RedirectView.as_view(pattern_name="grupos"),
        name="root",
    ),
]
