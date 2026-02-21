"""
Migration: Enrichment System

This migration:
1. Deletes the old ResearchTask model
2. Creates the new EnrichmentLog model
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("agents", "0011_add_submission_model"),
        ("auto_directory", "0002_researchtask_created_by"),
    ]

    operations = [
        # Delete old ResearchTask model
        migrations.DeleteModel(
            name="ResearchTask",
        ),
        # Create new EnrichmentLog model
        migrations.CreateModel(
            name="EnrichmentLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "previous_data",
                    models.JSONField(help_text="Agent data snapshot before enrichment"),
                ),
                (
                    "extracted_data",
                    models.JSONField(help_text="Raw data extracted from Firecrawl"),
                ),
                (
                    "applied_fields",
                    models.JSONField(
                        default=list,
                        help_text="List of field names that were actually updated",
                    ),
                ),
                (
                    "success",
                    models.BooleanField(
                        default=True,
                        help_text="Whether the enrichment completed successfully",
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        help_text="Error details if enrichment failed",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agent",
                    models.ForeignKey(
                        help_text="Agent that was enriched",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enrichment_logs",
                        to="agents.agent",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who triggered the enrichment",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="enrichment_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Enrichment Log",
                "verbose_name_plural": "Enrichment Logs",
                "ordering": ["-created_at"],
            },
        ),
        # Add indexes
        migrations.AddIndex(
            model_name="enrichmentlog",
            index=models.Index(
                fields=["agent", "-created_at"],
                name="auto_direct_agent_i_abc123_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="enrichmentlog",
            index=models.Index(
                fields=["success"],
                name="auto_direct_success_def456_idx",
            ),
        ),
    ]

