# backend/vota_backend/settings.py
"""
Django settings for the Voice of the Ancients backend.
"""
from pathlib import Path
from decouple import config
import os
import sys

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Security settings
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = True  # Enable debug for local development
ALLOWED_HOSTS = [
    "voiceoftheancients.ca",
    "www.voiceoftheancients.ca",
    "127.0.0.1",  # Add for local development
    "localhost",
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "translations.apps.TranslationsConfig",
    "rest_framework",
    "corsheaders",
]

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "vota_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "vota_backend.wsgi.application"

# Database configuration (SQLite for Django, pymongo for MongoDB)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    "sqlite": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:" if "test" in sys.argv else BASE_DIR / "translations.db",
    },
}

# Password validation
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

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (for future frontend)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Security settings
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS settings
CORS_ALLOW_ALL_ORIGINS = False  # Disable allow all origins for security
CORS_ALLOWED_ORIGINS = [
    "http://voiceoftheancients.ca",
    "https://voiceoftheancients.ca",
    "http://localhost:3000",  # Add for React frontend during development
    "http://127.0.0.1:3000",
]
