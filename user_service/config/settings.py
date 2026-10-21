import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
SHARED_DIR = REPO_ROOT / "shared"

if SHARED_DIR.exists():
    sys.path.insert(0, str(SHARED_DIR))


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-user-service-secret-key")
DEBUG = env_bool("DEBUG", True)
LOAD_TESTING = env_bool("LOAD_TESTING", False)
LOAD_TEST_OTP = os.getenv("LOAD_TEST_OTP", "246810")
LOAD_TEST_OTP_TTL_HOURS = int(os.getenv("LOAD_TEST_OTP_TTL_HOURS", "12"))
OTP_EMAIL_ENABLED = env_bool("OTP_EMAIL_ENABLED", True)
OTP_EXPOSE_IN_RESPONSE = env_bool("OTP_EXPOSE_IN_RESPONSE", DEBUG)
if LOAD_TESTING:
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
        "django.contrib.auth.hashers.Argon2PasswordHasher",
        "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
        "django.contrib.auth.hashers.ScryptPasswordHasher",
    ]
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_NAME = "dekstra_user_sessionid"
CSRF_COOKIE_NAME = "dekstra_user_csrftoken"
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "accounts",
    "registrasi",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "accounts.AuthAccount"


def database_config():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "user.sqlite3",
            }
        }

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL only supports postgres/postgresql for user_service")

    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
        }
    }


DATABASES = database_config()
DATABASES["default"]["CONN_MAX_AGE"] = int(os.getenv("DB_CONN_MAX_AGE", "60"))
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/registrasi-media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}
if LOAD_TESTING:
    REST_FRAMEWORK.update(
        {
            "DEFAULT_THROTTLE_CLASSES": (
                "rest_framework.throttling.AnonRateThrottle",
                "rest_framework.throttling.UserRateThrottle",
            ),
            "DEFAULT_THROTTLE_RATES": {
                "anon": os.getenv("AUTH_ANON_THROTTLE_RATE", "100000/min"),
                "user": os.getenv("AUTH_USER_THROTTLE_RATE", "100000/min"),
            },
        }
    )

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=int(os.getenv("ACCESS_TOKEN_DAYS", "3"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("REFRESH_TOKEN_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ROUTES = {
    "accounts.tasks.send_otp_email": {"queue": "otp"},
}

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "dev-internal-token")
