from django.apps import AppConfig


class SocialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'social'

    def ready(self):
        import social.signals  # Load the signals when the app starts
        from .models import ensure_approval_setting
        ensure_approval_setting()