# Generated manually on 2025-01-26

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("agents", "0010_agent_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agent",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("PUBLISHED", "Published"),
                    ("ARCHIVED", "Archived"),
                ],
                default="PUBLISHED",
                help_text="Agent visibility status",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="AgentSubmission",
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
                    "email",
                    models.EmailField(
                        help_text="Email of the person submitting the agent",
                        max_length=254,
                    ),
                ),
                (
                    "agent_name",
                    models.CharField(
                        help_text="Name of the agent being submitted", max_length=200
                    ),
                ),
                (
                    "agent_website",
                    models.URLField(
                        help_text="Website URL of the agent", max_length=255
                    ),
                ),
                (
                    "agent_description",
                    models.TextField(help_text="Description of the agent"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending Review"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="PENDING",
                        help_text="Current status of the submission",
                        max_length=20,
                    ),
                ),
                (
                    "reviewer_notes",
                    models.TextField(
                        blank=True, help_text="Internal notes from the reviewer"
                    ),
                ),
                (
                    "ai_review_result",
                    models.JSONField(
                        blank=True,
                        help_text="Results from AI review (for future use)",
                        null=True,
                    ),
                ),
                (
                    "submitted_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "agent",
                    models.ForeignKey(
                        blank=True,
                        help_text="The agent record created from this submission (if approved)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submissions",
                        to="agents.agent",
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        help_text="Admin user who reviewed this submission",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Agent Submission",
                "verbose_name_plural": "Agent Submissions",
                "ordering": ["-submitted_at"],
            },
        ),
    ]

