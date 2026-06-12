"""Django settings for the quiniela project (config)."""
import os
from pathlib import Path

from dotenv import load_dotenv

from config.get_env import getenv_bool, getenv_db, getenv_int, getenv_list

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

DEBUG = getenv_bool("DEBUG", True)

# Sin hosts declarados: comodín solo en local; vacío (cerrado) en prod.
ALLOWED_HOSTS = getenv_list("ALLOWED_HOSTS", ["*"] if DEBUG else [])

# Nginx termina el TLS y reenvía a gunicorn por HTTP. Sin esto Django
# cree que la petición es HTTP y el chequeo de Origin del CSRF rechaza
# los POST (403) cuando el navegador manda Origin https://.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = getenv_list("CSRF_TRUSTED_ORIGINS", [])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tournament",
    "pool",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pool.context_processors.standing",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

SESSION_COOKIE_SECURE = getenv_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = getenv_bool("CSRF_COOKIE_SECURE", not DEBUG)

DATABASES = {
    "default": getenv_db(
        env_pref="POSTGRES",
        sqlite_path=BASE_DIR / "db" / "app.sqlite3",
    )
}

AUTH_USER_MODEL = "pool.User"
LOGIN_URL = "login"

# football-data.org (API v4) — fuente de resultados.
FOOTBALL_DATA_API_TOKEN = os.environ.get("FOOTBALL_DATA_API_TOKEN", "")
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "NumericPasswordValidator",
    },
]

# Email SMTP configuration (Gmail) from environment.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("SMTP_SERVER", "")
EMAIL_PORT = getenv_int("SMTP_PORT", 587)
EMAIL_USE_SSL = EMAIL_PORT == 465
EMAIL_USE_TLS = EMAIL_PORT == 587
EMAIL_HOST_USER = os.environ.get("GMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("GMAIL_USER", "")

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
