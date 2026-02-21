from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "aiagents_directory.users"
    verbose_name = _("Users")

    def ready(self):
        try:
            import aiagents_directory.users.signals  # noqa: F401
        except ImportError:
            pass
