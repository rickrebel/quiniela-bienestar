"""Rutas de la app pool, montadas bajo ``/<slug>/`` (una quiniela).

El slug lo resuelve ``with_quiniela`` (ver ``pool/views/scope.py``) en cada
vista; aquí los patrones ya no lo mencionan. Una ventana de predicción se
identifica por su ``order`` dentro de la quiniela.
"""

from django.urls import path

from pool.views import leaderboard, predictions, progress, results, stages

urlpatterns = [
    path("reglas/", stages.reglas, name="reglas"),
    path("calendario/", stages.por_fecha_view, name="by_date"),
    path("posiciones/", leaderboard.leaderboard_view, name="standings"),
    path("historia/", progress.history_view, name="history"),
    path("grupos/", stages.groups_view, name="groups"),
    path("ventana/<int:order>/", stages.window_view, name="window"),
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
]
