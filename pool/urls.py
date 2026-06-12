"""Rutas de la app pool (quiniela)."""

from django.urls import path
from django.views.generic import RedirectView

from pool.views import auth, leaderboard, predictions, results, stages

urlpatterns = [
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    path(
        "recuperar/",
        auth.forgot_password_view,
        name="forgot_password",
    ),
    path(
        "recuperar/<uuid:key>/",
        auth.reset_password_view,
        name="reset_password",
    ),
    path("reglas/", stages.reglas, name="reglas"),
    path("posiciones/", leaderboard.leaderboard_view, name="standings"),
    path("stage/<str:key>/", stages.stage_view, name="stage"),
    path("save/", predictions.save_predictions, name="save"),
    path(
        "prediction/<int:match_id>/",
        predictions.save_prediction,
        name="save_prediction",
    ),
    path("send/", predictions.send_predictions, name="send"),
    path(
        "match/<int:match_id>/result/",
        results.record_result,
        name="record_result",
    ),
    path(
        "",
        RedirectView.as_view(url="/stage/GROUP_STAGE/"),
        name="root",
    ),
]
