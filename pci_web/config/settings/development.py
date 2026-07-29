from .base import *  # noqa: F401,F403

DEBUG = True
CSRF_TRUSTED_ORIGINS = ['https://*.serveo.net', 'https://zamintwin.ai', 'https://app.zamintwin.ai']
ALLOWED_HOSTS = ["*"]

# Use console email backend in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Debug toolbar (optional)
# INSTALLED_APPS += ["debug_toolbar"]
# MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
# INTERNAL_IPS = ["127.0.0.1"]
