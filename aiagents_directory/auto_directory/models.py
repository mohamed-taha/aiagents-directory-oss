"""
Auto-directory system models.

This module contains models for tracking:
- Agent enrichment operations (EnrichmentLog)
- Agent sourcing/discovery operations (SourcingRun)
"""

from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class EnrichmentLog(models.Model):
    """
    Audit trail for agent enrichment operations.
    
    Records what data was extracted from an agent's website and what
    fields were actually applied to the agent.
    
    Note: Only tracks existing Agent enrichments. Submission enrichments
    are stored in AgentSubmission.enrichment_data (single snapshot, no history).
    """
    
    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.CASCADE,
        related_name="enrichment_logs",
        help_text=_("Agent that was enriched")
    )
    
    previous_data = models.JSONField(
        help_text=_("Agent data snapshot before enrichment")
    )
    
    extracted_data = models.JSONField(
        help_text=_("Raw data extracted from Firecrawl")
    )
    
    applied_fields = models.JSONField(
        default=list,
        help_text=_("List of field names that were actually updated")
    )
    
    success = models.BooleanField(
        default=True,
        help_text=_("Whether the enrichment completed successfully")
    )
    
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text=_("Error details if enrichment failed")
    )
    
    created_at: datetime = models.DateTimeField(auto_now_add=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enrichment_logs",
        help_text=_("User who triggered the enrichment")
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Enrichment Log")
        verbose_name_plural = _("Enrichment Logs")
        indexes = [
            models.Index(fields=["agent", "-created_at"]),
            models.Index(fields=["success"]),
        ]

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} {self.agent.name} - {self.created_at:%Y-%m-%d %H:%M}"


class SourcingRun(models.Model):
    """
    Audit trail for automated agent sourcing operations.
    
    Records each run of a source plugin, including how many agents
    were discovered and how many were new (after deduplication).
    
    This helps track:
    - Which sources are producing the most agents
    - Success/failure rates of sourcing operations
    - When and how often sourcing runs occur
    """
    
    source_id = models.CharField(
        max_length=50,
        help_text=_("Identifier of the source plugin (e.g., 'serp', 'url')")
    )
    
    started_at: datetime = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the sourcing run started")
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the sourcing run completed (null if still running)")
    )
    
    discovered_count = models.IntegerField(
        default=0,
        help_text=_("Total number of agents discovered from the source")
    )
    
    new_count = models.IntegerField(
        default=0,
        help_text=_("Number of new agents after deduplication")
    )
    
    skipped_count = models.IntegerField(
        default=0,
        help_text=_("Number of agents skipped (duplicates)")
    )
    
    success = models.BooleanField(
        default=True,
        help_text=_("Whether the sourcing run completed successfully")
    )
    
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text=_("Error details if sourcing failed")
    )
    
    # Store configuration used for this run (queries, URLs, etc.)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Configuration/parameters used for this run")
    )
    
    # Store IDs of created submissions for reference
    created_submission_ids = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of AgentSubmission IDs created in this run")
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sourcing_runs",
        help_text=_("User who triggered the sourcing (null for automated runs)")
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("Sourcing Run")
        verbose_name_plural = _("Sourcing Runs")
        indexes = [
            models.Index(fields=["source_id", "-started_at"]),
            models.Index(fields=["success"]),
            models.Index(fields=["-started_at"]),
        ]

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} {self.source_id} - {self.started_at:%Y-%m-%d %H:%M} ({self.new_count} new)"
    
    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration of the run in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
