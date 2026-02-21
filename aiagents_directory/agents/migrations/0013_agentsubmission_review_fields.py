"""
Migration: Add review-related fields to AgentSubmission

Adds:
- source: Track how submission entered the system (FORM or AUTO)
- needs_manual_review: Flag for submissions needing human review
- Makes email optional (for automated sourcing)
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0012_agentsubmission_enrichment_data"),
    ]

    operations = [
        # Add source field
        migrations.AddField(
            model_name="agentsubmission",
            name="source",
            field=models.CharField(
                choices=[
                    ("FORM", "Submitted via Form"),
                    ("AUTO", "Automated Sourcing"),
                ],
                default="FORM",
                help_text="How this submission entered the system",
                max_length=20,
            ),
        ),
        # Add needs_manual_review flag
        migrations.AddField(
            model_name="agentsubmission",
            name="needs_manual_review",
            field=models.BooleanField(
                default=False,
                help_text="Flagged for manual review (low AI confidence or edge case)",
            ),
        ),
        # Make email optional
        migrations.AlterField(
            model_name="agentsubmission",
            name="email",
            field=models.EmailField(
                blank=True,
                help_text="Email of the person submitting the agent (required for FORM, optional for AUTO)",
                max_length=254,
                null=True,
            ),
        ),
    ]

