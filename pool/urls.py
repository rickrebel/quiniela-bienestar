"""Rutas de la app pool (quiniela)."""

from django.urls import path
from django.views.generic import RedirectView

from pool.views import auth, predictions, stages

urlpatterns = [
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    path("etapa/<str:key>/", stages.etapa, name="etapa"),
    path("save/", predictions.save_predictions, name="save"),
    path("send/", predictions.send_predictions, name="send"),
    path("confirm/", predictions.confirm_predictions, name="confirm"),
    path(
        "",
        RedirectView.as_view(url="/etapa/GROUP_STAGE/"),
        name="root",
    ),
]
