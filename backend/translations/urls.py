# backend/translations/urls.py
"""URL configuration for the translations app."""
from django.urls import path
from .views import (
    UpdateDictionaryView,
    EnglishToOjibweListView,
    OjibweToEnglishListView,
    SemanticMatchesView,
    MissingCommonTranslationsView,
)

urlpatterns = [
    path('update-dictionary/', UpdateDictionaryView.as_view(), name='update-dictionary'),
    path('english-to-ojibwe/', EnglishToOjibweListView.as_view(), name='english-to-ojibwe'),
    path('ojibwe-to-english/', OjibweToEnglishListView.as_view(), name='ojibwe-to-english'),
    path('semantic-matches/', SemanticMatchesView.as_view(), name='semantic-matches'),
    path('missing-common-translations/', MissingCommonTranslationsView.as_view(), name='missing-common-translations'),
]