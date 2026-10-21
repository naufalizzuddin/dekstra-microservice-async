import os
import sys
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = BASE_DIR.parent / "shared"

if SHARED_DIR.exists():
    sys.path.insert(0, str(SHARED_DIR))


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-document-generation-worker-secret-key")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
TEMPLATE_SURAT_DIR = Path(os.getenv("TEMPLATE_SURAT_DIR", "/template_surat"))
LIBREOFFICE_BIN = os.getenv("LIBREOFFICE_BIN", "soffice")
LIBREOFFICE_TIMEOUT_SECONDS = int(os.getenv("LIBREOFFICE_TIMEOUT_SECONDS", "60"))
KEPALA_DESA_NAMA = os.getenv("KEPALA_DESA_NAMA", "Kepala Desa")
KEPALA_DESA_NIP = os.getenv("KEPALA_DESA_NIP", "-")
REPORTING_SERVICE_URL = os.getenv(
    "REPORTING_SERVICE_URL",
    os.getenv("DASHBOARD_SERVICE_URL", ""),
)

INSTALLED_APPS = [
    "surat",
]

MIDDLEWARE = []

ROOT_URLCONF = "config.urls"


def database_config():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "document_generation_worker.sqlite3",
            }
        }
    parsed = urlparse(database_url)
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ROUTES = {
    "surat.tasks.generate_document": {"queue": "document"},
}
