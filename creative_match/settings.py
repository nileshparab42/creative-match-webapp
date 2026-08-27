"""
Django settings for creative_match project.

Works in two modes, switched purely by environment variables:
  - Local dev:  DEBUG=True, DB over TCP to a local/public Postgres, no HTTPS enforcement.
  - Cloud Run:  DEBUG=False, DB over the Cloud SQL unix socket (or TCP), HTTPS enforced,
                static files served by WhiteNoise (no Dockerfile needed).

Nothing below hardcodes an environment. Copy `.env.example` to `.env` for local dev;
on Cloud Run, set the same names as service environment variables / secrets.
"""

from pathlib import Path
import os

# python-dotenv is optional. On Cloud Run you set real env vars, so it's a no-op there.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


BASE_DIR = Path(__file__).resolve().parent.parent

# Cloud Run sets K_SERVICE for every deployed revision. We use its presence to
# pick sane defaults (e.g. DEBUG off) even if someone forgets to set DEBUG explicitly.
IS_CLOUD_RUN = "K_SERVICE" in os.environ


# ---------------------------------------------------------------------------
# Core security settings
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    # Fallback ONLY so `manage.py` doesn't hard-crash with no .env at all.
    # Always set DJANGO_SECRET_KEY explicitly in Cloud Run (Secret Manager).
    "django-insecure-local-dev-only-change-me" if not IS_CLOUD_RUN else "",
)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY environment variable is required in production.")

DEBUG = env_bool("DJANGO_DEBUG", default=not IS_CLOUD_RUN)

# Cloud Run gives every revision a *.a.run.app hostname; add your custom domain(s)
# via DJANGO_ALLOWED_HOSTS (comma separated) once you map one.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CLOUD_RUN_SERVICE_URL = os.environ.get("CLOUD_RUN_SERVICE_URL", "")  # e.g. https://xyz-uc.a.run.app
if CLOUD_RUN_SERVICE_URL:
    ALLOWED_HOSTS.append(CLOUD_RUN_SERVICE_URL.replace("https://", "").replace("http://", ""))
# Belt-and-braces: allow any *.run.app host so first deploys work before you've
# copied the exact URL into an env var. Safe because Cloud Run still terminates
# TLS and routes only your own service to that hostname.
ALLOWED_HOSTS.append(".run.app")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if CLOUD_RUN_SERVICE_URL and CLOUD_RUN_SERVICE_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(CLOUD_RUN_SERVICE_URL)
CSRF_TRUSTED_ORIGINS.append("https://*.run.app")

LOGIN_URL = "/"
LOGIN_REDIRECT_URL = "/home/"

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.sites",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    "creative_match",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files directly from the Cloud Run container —
    # no separate static host/CDN needed, and it's a no-op-safe addition locally too.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "creative_match.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "creative_match.wsgi.application"


# ---------------------------------------------------------------------------
# Database
#
# Local dev:  set DB_HOST to a normal IP/hostname (TCP).
# Cloud Run + Cloud SQL Auth Proxy sidecar/socket: set INSTANCE_CONNECTION_NAME
#   (e.g. "my-project:us-central1:my-instance") and the DB will connect over
#   the unix socket Cloud Run mounts at /cloudsql/<INSTANCE_CONNECTION_NAME>.
# Cloud Run + Cloud SQL public IP (no socket): just set DB_HOST to the public
#   IP, same as local — this matches your current setup and needs no extra
#   Cloud SQL wiring, only "Public IP" + an authorized network on the instance.
# ---------------------------------------------------------------------------

INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME", "")

if INSTANCE_CONNECTION_NAME:
    DB_HOST = f"/cloudsql/{INSTANCE_CONNECTION_NAME}"
else:
    DB_HOST = os.environ.get("DB_HOST", "34.14.171.35")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "ga4_creds_db"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": DB_HOST,
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# collectstatic (run automatically by the Cloud Run buildpack, see Procfile)
# writes here; WhiteNoise then serves straight from this folder.
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Production-only hardening (skipped automatically when DEBUG=True locally)
# ---------------------------------------------------------------------------

if not DEBUG:
    # Cloud Run terminates TLS at its load balancer and forwards this header,
    # so Django needs to trust it to know the original request was HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # 1 week; raise once you're confident
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Cloud Run captures stdout/stderr into Cloud Logging automatically — no file
# handlers needed, just make sure Django logs go to the console.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
}
