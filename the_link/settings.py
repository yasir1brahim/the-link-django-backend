"""
Django settings for The Link project.

For more information on this file, see
https://docs.djangoproject.com/en/stable/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/stable/ref/settings/
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
import environ
from django.utils.translation import gettext_lazy

# Build paths inside the project like this: BASE_DIR / "subdir".
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env"))

ENVIRONMENT = os.environ.get("ENVIRONMENT", default="production")
print(f"ENVIRONMENT: {ENVIRONMENT}")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("SECRET_KEY", default="django-insecure-BUNZkldzVq9rkiYkKT3rDl9MAJcZLvSKDbao7DV0")

# SECURITY WARNING: don"t run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", default=False)
if ENVIRONMENT == 'local':
    USE_HTTPS = False
else:
    USE_HTTPS = True
ENABLE_DEBUG_TOOLBAR = os.environ.get("ENABLE_DEBUG_TOOLBAR", default=False) and "test" not in sys.argv

# Note: It is not recommended to set ALLOWED_HOSTS to "*" in production
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", default=["*"])
print(f"DEBUG: {DEBUG}")
print(f"ENABLE_DEBUG_TOOLBAR: {ENABLE_DEBUG_TOOLBAR}")

# Application definition

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.admindocs",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sitemaps",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.forms",
]

# Put your third-party apps here
THIRD_PARTY_APPS = [
    "allauth",  # allauth account/registration management
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",
    "whitenoise.runserver_nostatic",
    "channels",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "allauth.mfa",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt",
    "corsheaders",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    "drf_spectacular",
    "rest_framework_api_key",
    "celery_progress",
    "hijack",  # "login as" functionality
    "hijack.contrib.admin",  # hijack buttons in the admin
    "djstripe",  # stripe integration
    "waffle",
    "health_check",
    "health_check.db",
    "health_check.contrib.celery",
    "health_check.contrib.redis",
    "django_celery_beat",
]

PEGASUS_APPS = [
    # "pegasus.apps.examples.apps.PegasusExamplesConfig",
    # "pegasus.apps.employees.apps.PegasusEmployeesConfig",
]

# Put your project-specific apps here
PROJECT_APPS = [
    "apps.authentication.apps.AuthenticationConfig",
    # "apps.group_chat",
    "apps.subscriptions.apps.SubscriptionConfig",
    "apps.users.apps.UserConfig",
    # "apps.dashboard.apps.DashboardConfig",
    "apps.api.apps.APIConfig",
    # "apps.ecommerce.apps.ECommerceConfig",
    "apps.web",
    "apps.teams.apps.TeamConfig",
    # "apps.teams_example.apps.TeamsExampleConfig",
    "apps.deliverables.apps.DeliverablesConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + PEGASUS_APPS + PROJECT_APPS

if DEBUG:
    # in debug mode, add daphne to the beginning of INSTALLED_APPS to enable async support
    INSTALLED_APPS.insert(0, "daphne")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.teams.middleware.TeamsMiddleware",
    "apps.web.locale_middleware.UserLocaleMiddleware",
    "apps.web.locale_middleware.UserTimezoneMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "hijack.middleware.HijackUserMiddleware",
    "waffle.middleware.WaffleMiddleware",
]

if ENABLE_DEBUG_TOOLBAR:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INSTALLED_APPS.append("debug_toolbar")
    INTERNAL_IPS = ["127.0.0.1"]
    try:
        import socket

        # get hostname for Docker environments
        # See https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#configure-internal-ips
        hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
        # add discovered IPs plus some common defaults
        INTERNAL_IPS += [ip[: ip.rfind(".")] + ".1" for ip in ips] + ["192.168.65.1", "10.0.2.2"]
    except OSError as e:
        print(f"{e} while attempting to resolve system hostname. Using INTERNAL_IPS={INTERNAL_IPS}")

ROOT_URLCONF = "the_link.urls"


# used to disable the cache in dev, but turn it on in production.
# more here: https://nickjanetakis.com/blog/django-4-1-html-templates-are-cached-by-default-with-debug-true
_DEFAULT_LOADERS = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]

_CACHED_LOADERS = [("django.template.loaders.cached.Loader", _DEFAULT_LOADERS)]


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            "loaders": _DEFAULT_LOADERS if DEBUG else _CACHED_LOADERS,
        },
    },
]

WSGI_APPLICATION = "the_link.wsgi.application"

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# Database
# https://docs.djangoproject.com/en/stable/ref/settings/#databases

DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Auth / login stuff

# Django recommends overriding the user model even if you don"t think you need to because it makes
# future changes much easier.
AUTH_USER_MODEL = "users.CustomUser"
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"

# Password validation
# https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators

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

# Allauth setup

ACCOUNT_ADAPTER = "apps.teams.adapter.AcceptInvitationAdapter"
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False  # don't send "forgot password" emails to unknown accounts
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = False
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
# Authenticate if local account with this email address already exists
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
# Connect local account and social account if local account with that email address already exists
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

ACCOUNT_FORMS = {
    "signup": "apps.teams.forms.TeamSignupForm",
}
SOCIALACCOUNT_FORMS = {
    "signup": "apps.users.forms.CustomSocialSignupForm",
}


# User signup configuration: change to "mandatory" to require users to confirm email before signing in.
# or "optional" to send confirmation emails but not require them
ACCOUNT_EMAIL_VERIFICATION = os.environ.get("ACCOUNT_EMAIL_VERIFICATION", default="none")

AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",
    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend",
)

ELLIS_DON_SSO_CLIENT_ID = os.environ.get("ELLIS_DON_SSO_CLIENT_ID")
ELLIS_DON_SSO_CLIENT_SECRET = os.environ.get("ELLIS_DON_SSO_CLIENT_SECRET")
ELLIS_DON_SSO_TENANT_ID = os.environ.get("ELLIS_DON_SSO_TENANT_ID")
ELLIS_DON_SSO_ORGANIZATION_DOMAIN = "ellisdon.com"
print(f"ELLIS_DON_SSO_CLIENT_ID: {ELLIS_DON_SSO_CLIENT_ID}")
THE_LINK_SSO_CLIENT_ID = os.environ.get("THE_LINK_SSO_CLIENT_ID")
THE_LINK_SSO_CLIENT_SECRET = os.environ.get("THE_LINK_SSO_CLIENT_SECRET")
THE_LINK_SSO_TENANT_ID = os.environ.get("THE_LINK_SSO_TENANT_ID")
THE_LINK_SSO_ORGANIZATION_DOMAIN = "thelink.ai"
print(f"THE_LINK_SSO_CLIENT_ID: {THE_LINK_SSO_CLIENT_ID}")
SOCIALACCOUNT_ADAPTER = "apps.authentication.api_views.MicrosoftSSOSocialAccountAdapter"
# enable social login
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
    },
    'microsoft': {
        'TENANT': 'organizations',  # or 'common', 'consumers', or your tenant ID
        'APPS': [
            {
                'client_id': ELLIS_DON_SSO_CLIENT_ID,
                'secret': ELLIS_DON_SSO_CLIENT_SECRET,
                'settings': {
                    'tenant': ELLIS_DON_SSO_TENANT_ID,
                },
            },
            {
                'client_id': THE_LINK_SSO_CLIENT_ID,
                'secret': THE_LINK_SSO_CLIENT_SECRET,
                'settings': {
                    'tenant': THE_LINK_SSO_TENANT_ID,
                },
            }
        ],
        "VERIFIED_EMAIL": True,
        "EMAIL_AUTHENTICATION_AUTO_CONNECT": True
    }
}
DOMAINS_CONFIGURED_FOR_SSO = ['thelink.ai', 'ellisdon.com']

# For turnstile captchas
TURNSTILE_KEY = os.environ.get("TURNSTILE_KEY", default=None)
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET", default=None)


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = "en-us"
LANGUAGE_COOKIE_NAME = "the_link_language"
LANGUAGES = [
    ("en", gettext_lazy("English")),
    ("fr", gettext_lazy("French")),
]
LOCALE_PATHS = (BASE_DIR / "locale",)

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATIC_ROOT = BASE_DIR / "static_root"
STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # swap these to use manifest storage to bust cache when files change
        # note: this may break image references in sass/css files which is why it is not enabled by default
        # "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# Default primary key field type
# https://docs.djangoproject.com/en/stable/ref/settings/#default-auto-field

# future versions of Django will use BigAutoField as the default, but it can result in unwanted library
# migration files being generated, so we stick with AutoField for now.
# change this to BigAutoField if you"re sure you want to use it and aren"t worried about migrations.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Removes deprecation warning for future compatibility.
# see https://adamj.eu/tech/2023/12/07/django-fix-urlfield-assume-scheme-warnings/ for details.
FORMS_URLFIELD_ASSUME_HTTPS = True

# Email setup

# default email used by your server
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", default="noreply@tlsignup.com")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", default="noreply@tlsignup.com")

# The default value will print emails to the console, but you can change that here
# and in your environment.
if ENVIRONMENT == 'local':
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"

# Most production backends will require further customization. The below example uses Mailgun.
ANYMAIL = {
    "SENDGRID_API_KEY": os.environ.get("SENDGRID_API_KEY", default=None),
}


EMAIL_SUBJECT_PREFIX = "[The Link] "

# Django sites

SITE_ID = 1

# DRF config
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ("apps.api.permissions.IsAuthenticatedOrHasUserAPIKey",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=4),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=8),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": os.environ.get("SIMPLE_JWT_SIGNING_KEY", default="<a complex signing key>"),
    "ALGORITHM": "HS512",
}

REST_AUTH = {
    "USE_JWT": True,
    "JWT_AUTH_HTTPONLY": False,
    "USER_DETAILS_SERIALIZER": "apps.users.serializers.CustomUserSerializer",
    "PASSWORD_RESET_USE_SITES_DOMAIN": True,
}

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", default="http://localhost:3000")

CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", default="http://localhost:5173," + FRONTEND_BASE_URL).split(",")
CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", default="http://localhost:8000,https://app-dj-qa-api.thelink.ai,https://log-manager-api-prod.thelink.ai").split(",")

SPECTACULAR_SETTINGS = {
    "TITLE": "The Link",
    "DESCRIPTION": "Web application for The Link.ai",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
        "displayOperationId": True,
    },
    "PREPROCESSING_HOOKS": [
        "apps.api.schema.filter_schema_apis",
    ],
    "APPEND_COMPONENTS": {
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "Authorization"}}
    },
    "SECURITY": [
        {
            "ApiKeyAuth": [],
        }
    ],
    "ENUM_NAME_OVERRIDES": {
        "ProjectMembershipRole": "apps.deliverables.models.PROJECT_MEMBERSHIP_ROLE_CHOICES",
        "TeamMembershipRole": "apps.teams.roles.ROLE_CHOICES",
        "ProjectStatus": "apps.deliverables.models.Project.PROJECT_STATUS_CHOICES",
    }
}

ENUM_NAME_OVERRIDES = {
    "apps.deliverables.models.ProjectMembership.role": "ProjectMembershipRole",
    "apps.teams.models.TeamMembership.role": "TeamMembershipRole"
}

# Celery setup (using redis)
if os.environ.get("REDIS_URL"):
    REDIS_URL = os.environ.get("REDIS_URL")
elif os.environ.get("REDIS_TLS_URL"):
    REDIS_URL = os.environ.get("REDIS_TLS_URL")
else:
    REDIS_HOST = os.environ.get("REDIS_HOST", default="localhost")
    REDIS_PORT = os.environ.get("REDIS_PORT", default="6379")
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

if REDIS_URL.startswith("rediss"):
    REDIS_URL = f"{REDIS_URL}?ssl_cert_reqs=none"

CELERY_BROKER_URL = CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# see pegasus/apps/examples/migrations/0001_celery_tasks.py for example scheduled tasks
# see apps/subscriptions/migrations/0001_celery_tasks.py for scheduled tasks

# Channels / Daphne setup

ASGI_APPLICATION = "the_link.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Health Checks
# A list of tokens that can be used to access the health check endpoint
HEALTH_CHECK_TOKENS = os.environ.get("HEALTH_CHECK_TOKENS", default="")

# Waffle config

WAFFLE_FLAG_MODEL = "teams.Flag"

# Pegasus config

# replace any values below with specifics for your project
PROJECT_METADATA = {
    "NAME": gettext_lazy("The Link"),
    "URL": "http://thelink.ai",
    "DESCRIPTION": gettext_lazy("Web application for The Link.ai"),
    "IMAGE": "https://upload.wikimedia.org/wikipedia/commons/2/20/PEO-pegasus_black.svg",
    "KEYWORDS": "SaaS, django",
    "CONTACT_EMAIL": "avery.pawelek@thelink.ai",
}

# set this to True in production to have URLs generated with https instead of http
if ENVIRONMENT == 'local':
    USE_HTTPS_IN_ABSOLUTE_URLS = False
else:
    USE_HTTPS_IN_ABSOLUTE_URLS = True

if ENVIRONMENT == 'local':
    ADMINS = []
else:
    ADMINS = [("Avery Pawelek", "avery.pawelek@thelink.ai")]

# Add your google analytics ID to the environment to connect to Google Analytics
GOOGLE_ANALYTICS_ID = os.environ.get("GOOGLE_ANALYTICS_ID", default="")


# Stripe config
# modeled to be the same as https://github.com/dj-stripe/dj-stripe
# Note: don"t edit these values here - edit them in your .env file or environment variables!
# The defaults are provided to prevent crashes if your keys don"t match the expected format.
STRIPE_LIVE_PUBLIC_KEY = os.environ.get("STRIPE_LIVE_PUBLIC_KEY", default="pk_live_***")
STRIPE_LIVE_SECRET_KEY = os.environ.get("STRIPE_LIVE_SECRET_KEY", default="sk_live_***")
STRIPE_TEST_PUBLIC_KEY = os.environ.get("STRIPE_TEST_PUBLIC_KEY", default="pk_test_***")
STRIPE_TEST_SECRET_KEY = os.environ.get("STRIPE_TEST_SECRET_KEY", default="sk_test_***")
# Change to True in production
STRIPE_LIVE_MODE = os.environ.get("STRIPE_LIVE_MODE", False)

# djstripe settings
# Get it from the section in the Stripe dashboard where you added the webhook endpoint
# or from the stripe CLI when testing
DJSTRIPE_WEBHOOK_SECRET = os.environ.get("DJSTRIPE_WEBHOOK_SECRET", default="whsec_***")

DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"  # change to "djstripe_id" if not a new installation
DJSTRIPE_SUBSCRIBER_MODEL = "teams.Team"
DJSTRIPE_SUBSCRIBER_MODEL_REQUEST_CALLBACK = lambda request: request.team  # noqa E731

ACTIVE_ECOMMERCE_PRODUCT_IDS = os.environ.get("ACTIVE_ECOMMERCE_PRODUCT_IDS", default=[])

SILENCED_SYSTEM_CHECKS = [
    "djstripe.I002",  # Pegasus uses the same settings as dj-stripe for keys, so don't complain they are here
]

# Sentry setup

# populate this to configure sentry. should take the form: "https://****@sentry.io/12345"
SENTRY_DSN = os.environ.get("SENTRY_DSN", default="")


if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()])

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": '[{asctime}] {levelname} "{name}" {message}',
            "style": "{",
            "datefmt": "%d/%b/%Y %H:%M:%S",  # match Django server time format
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler'
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "mail_admins"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", default="INFO"),
        },
        "the_link": {
            "handlers": ["console"],
            "level": os.environ.get("THE_LINK_LOG_LEVEL", default="INFO"),
        },
    },
}

DATA_UPLOAD_MAX_NUMBER_FILES = 250

BACKEND_CALLBACK_URL = os.environ.get("BACKEND_CALLBACK_URL", default="http://localhost:8000")

LEGACY_DB_HOST = os.environ.get("LEGACY_DB_HOST", default="deliverables-dev.cdrdfhibqqqq.us-east-1.rds.amazonaws.com")
LEGACY_DB_PORT = os.environ.get("LEGACY_DB_PORT", default="3306")
LEGACY_DB_USER = os.environ.get("LEGACY_DB_USER", default="admin")
LEGACY_DB_PASSWORD = os.environ.get("LEGACY_DB_PASSWORD", default="")
LEGACY_DB_NAME = os.environ.get("LEGACY_DB_NAME", default="logmaker")

AWS_REGION = os.environ.get("AWS_REGION", default="us-east-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", default="")
S3_BUCKET = os.environ.get("S3_BUCKET", default="")
LAMBDA_FUNCTION_URL = os.environ.get("LAMBDA_FUNCTION_URL", default="")
V2_PROCESS_DELIVERABLES_LAMBDA_FUNCTION_URL = os.environ.get("V2_PROCESS_DELIVERABLES_LAMBDA_FUNCTION_URL", default="")
FULL_SPEC_PROCESSING_LAMBDA_FUNCTION_URL = V2_PROCESS_DELIVERABLES_LAMBDA_FUNCTION_URL

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", default="")
BACKEND_CALLBACK_URL = BACKEND_BASE_URL + "/api/deliverables/spec-status-webhook/"

NOTICES_LAMBDA_FUNCTION_URL = os.environ.get("NOTICES_LAMBDA_FUNCTION_URL", default="")
BACKEND_NOTICES_CALLBACK_URL = BACKEND_BASE_URL + "/api/deliverables/webhooks/notice-processing/"
BACKEND_FULL_SPEC_PROCESSING_CALLBACK_URL = BACKEND_BASE_URL + "/api/deliverables/webhooks/full-spec-processing/"
NOTICES_FEATURE_FLAG_NAME = 'notices'
VERSIONING_FEATURE_FLAG_NAME = 'versioning'
VERSIONING_SUBMITTAL_COMPARISON_FEATURE_FLAG_NAME = 'versioning_submittal_comparison'
V2_PROCESS_DELIVERABLES_FEATURE_FLAG_NAME = 'v2_process_deliverables'
FULL_SPEC_PROCESSING_FEATURE_FLAG_NAME = 'full_spec_processing'
SPECGPT_FEATURE_FLAG_NAME = 'specgpt'
INSPECTION_LOG_FEATURE_FLAG_NAME = 'inspection_log'
INSPECTION_LOG_USE_DATA_TABLES_FEATURE_FLAG_NAME = 'inspection_log_use_data_tables'
QA_PLANNER_FEATURE_FLAG_NAME = 'qa_planner'
SPEC_CENTERED_VIEW_FEATURE_FLAG_NAME = 'spec_centered_view'

PROCORE_CLIENT_ID = os.environ.get("PROCORE_CLIENT_ID", default="")
PROCORE_CLIENT_SECRET = os.environ.get("PROCORE_CLIENT_SECRET", default="")
PROCORE_REDIRECT_URL = os.environ.get("PROCORE_REDIRECT_URL", default="")
PROCORE_AUTH_BASE_URL = os.environ.get("PROCORE_AUTH_BASE_URL", default="")
PROCORE_BASE_URL = os.environ.get("PROCORE_BASE_URL", default="")

SPECGPT_CHUNK_SIZE = 1000
SPECGPT_CHUNK_OVERLAP = 200
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", default="")
BACKEND_SPECGPT_CALLBACK_URL = BACKEND_BASE_URL + "/api/deliverables/webhooks/specgpt-embedding/"
MAX_CHAT_MESSAGES = 10

PROMPTLAYER_API_KEY = os.environ.get("PROMPTLAYER_API_KEY", default="")
SPEC_GPT_PROMPTLAYER_PROMPT_NAME = "specgpt"
INSPECTION_LOG_PROMPTLAYER_PROMPT_NAME = "inspection_log"
OWNER_DELIVERABLES_PROMPTLAYER_PROMPT_NAME = "owner_deliverables"
GENERATE_LOG_LAMBDA_FUNCTION_URL = os.environ.get("GENERATE_LOG_LAMBDA_FUNCTION_URL", default="https://v4aiai3ftopjpvbdtonytus3c40wbojq.lambda-url.us-east-1.on.aws/")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", default="")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", default="")

# OpenAI model context settings
OPENAI_MODEL_MAX_CONTEXT_SIZE = 1000000 # in tokens
BACKEND_AI_LOG_CALLBACK_URL = BACKEND_BASE_URL + "/api/deliverables/webhooks/ai-log-generation/"
