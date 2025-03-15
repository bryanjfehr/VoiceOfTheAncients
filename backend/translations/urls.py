"""URL configuration for the translations app."""
from django.urls import path
from . import views

urlpatterns = [
    path("gaps/", views.get_gaps, name="get_gaps"),
]
