"""
Migration: Add enrichment_data field to AgentSubmission

This field stores enrichment data from Firecrawl scraping before
the submission is approved and an Agent is created.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0011_add_submission_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentsubmission",
            name="enrichment_data",
            field=models.JSONField(
                blank=True,
                help_text="Enrichment data from Firecrawl scraping (URLs and extracted content)",
                null=True,
            ),
        ),
    ]

