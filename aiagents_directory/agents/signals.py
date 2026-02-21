"""
Signals to auto-request indexing when agents are published.
"""
import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Agent
from .constants import AgentStatus

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Agent)
def capture_old_status(sender, instance, **kwargs):
    """Capture the old status before save to detect status transitions."""
    if instance.pk:
        try:
            instance._old_status = Agent.objects.get(pk=instance.pk).status
        except Agent.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Agent)
def index_published_agent(sender, instance, created, **kwargs):
    """Request indexing when an agent is newly published.

    Triggers when:
    - New agent created with PUBLISHED status
    - Existing agent status changes to PUBLISHED
    """
    if instance.status != AgentStatus.PUBLISHED:
        return

    old_status = getattr(instance, "_old_status", None)

    # Skip if already published (just an edit, not a status change)
    if not created and old_status == AgentStatus.PUBLISHED:
        return

    # Import here to avoid circular imports
    from aiagents_directory.utils.indexing import request_indexing

    try:
        # Agent detail page
        request_indexing(f"/{instance.slug}/")

        # Also re-index the browse page since it has new content
        request_indexing("/browse/")
    except Exception as e:
        logger.error(f"Failed to request indexing for agent {instance.slug}: {e}")
