"""Rutas de autenticación (globales, sin prefijo de quiniela).

El acceso ocurre antes de conocer la quiniela activa, así que login,
registro, logout y recuperación viven fuera del prefijo ``/<slug>/``. El
link de recuperación (con ``SITE_URL``) sigue siendo global.
"""

from django.urls import path

from pool.views import auth

urlpatterns = [
    path("login/", auth.login_view, name="login"),
    path("registro/", auth.register_view, name="register"),
    path("logout/", auth.logout_view, name="logout"),
    path("recuperar/", auth.forgot_password_view, name="forgot_password"),
    path(
        "recuperar/<uuid:key>/",
        auth.reset_password_view,
        name="reset_password",
    ),
]
