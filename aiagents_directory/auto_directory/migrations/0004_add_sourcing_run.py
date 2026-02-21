# Generated manually for SourcingRun model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auto_directory", "0003_enrichment_system"),
    ]

    operations = [
        migrations.CreateModel(
            name="SourcingRun",
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
                    "source_id",
                    models.CharField(
                        help_text="Identifier of the source plugin (e.g., 'serp', 'url')",
                        max_length=50,
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When the sourcing run started",
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the sourcing run completed (null if still running)",
                        null=True,
                    ),
                ),
                (
                    "discovered_count",
                    models.IntegerField(
                        default=0,
                        help_text="Total number of agents discovered from the source",
                    ),
                ),
                (
                    "new_count",
                    models.IntegerField(
                        default=0,
                        help_text="Number of new agents after deduplication",
                    ),
                ),
                (
                    "skipped_count",
                    models.IntegerField(
                        default=0,
                        help_text="Number of agents skipped (duplicates)",
                    ),
                ),
                (
                    "success",
                    models.BooleanField(
                        default=True,
                        help_text="Whether the sourcing run completed successfully",
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        help_text="Error details if sourcing failed",
                        null=True,
                    ),
                ),
                (
                    "config",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Configuration/parameters used for this run",
                    ),
                ),
                (
                    "created_submission_ids",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of AgentSubmission IDs created in this run",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who triggered the sourcing (null for automated runs)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sourcing_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Sourcing Run",
                "verbose_name_plural": "Sourcing Runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="sourcingrun",
            index=models.Index(
                fields=["source_id", "-started_at"],
                name="auto_direct_source__8c7d4e_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="sourcingrun",
            index=models.Index(
                fields=["success"],
                name="auto_direct_success_e7f9a3_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="sourcingrun",
            index=models.Index(
                fields=["-started_at"],
                name="auto_direct_started_3b8f2a_idx",
            ),
        ),
    ]
