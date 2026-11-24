from pathlib import Path
import environ
import cloudinary
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")
SECRET_KEY = env("DJANGO_SECRET_KEY")
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY")
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_FALLBACK_MODEL = env("GEMINI_FALLBACK_MODEL", default="gemini-3.1-flash-lite")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:9000"]
)
CORS_ALLOW_CREDENTIALS = True
JWT_SIGNING_KEY = env("JWT_SIGNING_KEY")
CLOUDINARY_URL = env("CLOUDINARY_URL")
# Console backend by default so local dev works without SMTP credentials.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="ContentFlow AI <noreply@contentflow.ai>"
)
# Set to ~1.5 for SMTP sandboxes (Mailtrap) that reject mails sent back to back.
EMAIL_NOTIFICATION_DELAY_SECONDS = env.float("EMAIL_NOTIFICATION_DELAY_SECONDS", default=0)

SCRAPER_BLOCKED_DOMAINS = env.list(
    "SCRAPER_BLOCKED_DOMAINS",
    default=[
        "localhost",
        "127.0.0.1",
        "metadata.google.internal",
        "169.254.169.254",
        "metadata.aws.internal",
    ],
)

from config.sentry import configure_sentry

SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1)
SENTRY_SEND_DEFAULT_PII = env.bool("SENTRY_SEND_DEFAULT_PII", default=False)
configure_sentry(
    dsn=env("SENTRY_DSN", default=""),
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=SENTRY_SEND_DEFAULT_PII,
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cloudinary",
    "apps.users",
    "apps.jobs",
    "apps.stats",
    "apps.scheduling",
    "apps.evals",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
]
AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
    "config.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
        "DIRS": [BASE_DIR.parent / "frontend" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


DATABASES = {"default": env.db("DATABASE_URL")}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR.parent / "frontend" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Avatars live on Cloudinary, which reads CLOUDINARY_URL. Re-read it now that
# .env is loaded, and keep delivery URLs HTTPS behind Render's proxy.
cloudinary.reset_config()
cloudinary.config(secure=True)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.CookieJWTAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute",
        "user": "60/minute",
        "jobs_create_burst": "3/minute",
        "jobs_create_daily": "15/day",
        "scrape": "5/minute",
        "auth": "5/hour",
        "account_action": "30/hour",
        "scheduled_email_create": "20/hour",
    },
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # /outputs/ filters on ?format=, which DRF would otherwise read as a renderer suffix.
    "URL_FORMAT_OVERRIDE": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ContentFlow AI API",
    "DESCRIPTION": "AI-powered content repurposing platform that transforms blog posts into multiple social media formats",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {
        "name": "ContentFlow AI Support",
        "email": "support@contentflow.ai",
    },
    "LICENSE": {
        "name": "MIT",
    },
    "TAGS": [
        {"name": "jobs", "description": "Create and manage content generation jobs"},
        {
            "name": "outputs",
            "description": "Retrieve and rate generated content outputs",
        },
        {"name": "users", "description": "User authentication and management"},
        {"name": "stats", "description": "Usage statistics and analytics"},
    ],
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 1,
        "docExpansion": "none",
    },
    "SECURITY": [{"BearerAuth": []}],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT access token.",
            }
        }
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_COOKIE": "access_token",
    "AUTH_COOKIE_REFRESH": "refresh_token",
    "AUTH_COOKIE_SECURE": not DEBUG,
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_SAMESITE": "Strict",
}

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Console output in dev, JSON in production. Every record carries the request_id.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.middleware.RequestIDLogFilter"},
    },
    "formatters": {
        "console": {
            "format": "%(asctime)s %(levelname)s %(name)s [request_id=%(request_id)s] %(message)s",
        },
        "json": {
            "()": "config.logging_utils.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "console" if DEBUG else "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
