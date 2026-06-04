"""Rutas de la app pool (quiniela)."""

from django.urls import path
from django.views.generic import RedirectView

from pool.views import auth, predictions, stages

urlpatterns = [
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    path("stage/<str:key>/", stages.stage_view, name="stage"),
    path("save/", predictions.save_predictions, name="save"),
    path("send/", predictions.send_predictions, name="send"),
    # send = confirm
    # path("confirm/", predictions.confirm_predictions, name="confirm"),
    path(
        "",
        RedirectView.as_view(url="/stage/GROUP_STAGE/"),
        name="root",
    ),
]
