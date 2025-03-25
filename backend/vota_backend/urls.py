# backend/vota_backend/urls.py
"""
URL configuration for the VOTA backend project.
Maps API endpoints to the translations app.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('translations.urls')),  # Include translations URLs under /api/
]