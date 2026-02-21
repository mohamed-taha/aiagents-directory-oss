from django.apps import AppConfig


class NewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aiagents_directory.news"
    verbose_name = "News"

    def ready(self):
        from . import signals  # noqa: F401
