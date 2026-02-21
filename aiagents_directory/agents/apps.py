from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aiagents_directory.agents"
    verbose_name = "Agents"

    def ready(self):
        from . import signals  # noqa: F401
