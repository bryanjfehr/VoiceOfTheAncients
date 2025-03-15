"""WSGI configuration for the VOTA backend deployment."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vota_backend.settings")

application = get_wsgi_application()
