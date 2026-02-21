"""
Signals to auto-request indexing when news articles are created.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import NewsArticle

logger = logging.getLogger(__name__)


@receiver(post_save, sender=NewsArticle)
def index_news_pages(sender, instance, created, **kwargs):
    """Request indexing for news archive pages when new article is added."""
    if not created:
        return

    # Import here to avoid circular imports
    from aiagents_directory.utils.indexing import request_indexing

    # Index all 4 listing pages (not individual articles - we don't have detail pages)
    try:
        news_pages = [
            "/ai-agents-news/",
            "/ai-agents-news/today/",
            "/ai-agents-news/this-week/",
            "/ai-agents-news/this-month/",
        ]
        for page in news_pages:
            request_indexing(page)
    except Exception as e:
        logger.error(f"Failed to request indexing for news pages: {e}")
