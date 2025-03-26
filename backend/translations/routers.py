# backend/translations/routers.py
"""
Database router for directing models to specific databases.
"""

class DatabaseRouter:
    """
    A router to control database operations for models in the translations app.
    """
    def db_for_read(self, model, **hints):
        """Direct read operations to the appropriate database."""
        if model._meta.app_label == 'translations':
            if model._meta.model_name in ['semanticmatch', 'semanticmatchlocal']:
                return 'semantic_matches'
            elif model._meta.model_name in ['untranslatedword']:
                return 'untranslated_words'
            return 'translations'
        return None

    def db_for_write(self, model, **hints):
        """Direct write operations to the appropriate database."""
        if model._meta.app_label == 'translations':
            if model._meta.model_name in ['semanticmatch', 'semanticmatchlocal']:
                return 'semantic_matches'
            elif model._meta.model_name in ['untranslatedword']:
                return 'untranslated_words'
            return 'translations'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations if objects are in the same database."""
        db_list = ('translations', 'semantic_matches', 'untranslated_words')
        if obj1._state.db in db_list and obj2._state.db in db_list:
            return obj1._state.db == obj2._state.db
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Ensure migrations are applied to the correct database."""
        if app_label == 'translations':
            if model_name in ['semanticmatch', 'semanticmatchlocal']:
                return db == 'semantic_matches'
            elif model_name == 'untranslatedword':
                return db == 'untranslated_words'
            return db == 'translations'
        return None
