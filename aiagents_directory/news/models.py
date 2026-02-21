from django.db import models
from django.utils import timezone


class NewsArticle(models.Model):
    """A news article about AI agents."""

    title = models.CharField(max_length=500)
    summary = models.TextField(max_length=2000, blank=True)
    url = models.URLField(max_length=2000, unique=True)
    source_domain = models.CharField(max_length=255, blank=True)
    published_at = models.DateTimeField(
        help_text="Article's publish date (from source)"
    )
    scraped_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When we discovered this article"
    )
    search_query = models.CharField(
        max_length=255,
        blank=True,
        help_text="The search query that found this article"
    )

    class Meta:
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["-published_at"]),
            models.Index(fields=["source_domain"]),
        ]

    def __str__(self):
        return self.title[:80]

    @property
    def source_name(self) -> str:
        """Human-friendly source name derived from domain."""
        if not self.source_domain:
            return "Unknown"
        # Remove www. prefix and common TLDs for display
        name = self.source_domain.lower()
        if name.startswith("www."):
            name = name[4:]
        # Capitalize first letter of each part
        return name.split(".")[0].title()


class NewsFetchRun(models.Model):
    """Audit log for news fetch operations."""

    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    articles_found = models.IntegerField(default=0)
    articles_created = models.IntegerField(default=0)
    articles_skipped = models.IntegerField(default=0)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    queries_used = models.JSONField(
        default=list,
        help_text="List of search queries used in this run"
    )
    tbs_filter = models.CharField(
        max_length=50,
        blank=True,
        help_text="Time-based search filter used (e.g., qdr:d)"
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"NewsFetchRun {self.started_at:%Y-%m-%d %H:%M} - {status}"

    def mark_complete(self, success: bool = True, error: str = ""):
        """Mark this run as complete."""
        self.completed_at = timezone.now()
        self.success = success
        self.error_message = error
        self.save()
