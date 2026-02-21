"""
Enrich pending agent submissions using Firecrawl.

Usage:
    # Enrich all new submissions (not yet enriched)
    python manage.py enrich_submissions

    # Enrich specific submissions by ID
    python manage.py enrich_submissions --ids 1 2 3

    # Limit number processed
    python manage.py enrich_submissions --limit 5

    # Add delay between requests (rate limiting)
    python manage.py enrich_submissions --delay 2
"""

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import QuerySet

from aiagents_directory.agents.models import AgentSubmission, SubmissionStatus
from aiagents_directory.auto_directory.services import EnrichmentService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Enrich pending agent submissions with Firecrawl"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--ids",
            type=int,
            nargs="+",
            help="Specific submission IDs to enrich",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of submissions to process",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Delay in seconds between requests (default: 1.0)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-enrich even if already enriched",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def get_submissions(self, **options: Any) -> QuerySet[AgentSubmission]:
        """Build queryset based on options."""
        qs = AgentSubmission.objects.filter(status=SubmissionStatus.PENDING)

        if options["ids"]:
            qs = qs.filter(id__in=options["ids"])
            self.stdout.write(f"Filtering by IDs: {options['ids']}")

        if not options["force"]:
            # Only submissions without enrichment data
            qs = qs.filter(enrichment_data__isnull=True)

        # Must have a website
        qs = qs.exclude(agent_website="").exclude(agent_website__isnull=True)

        if options["limit"]:
            qs = qs[: options["limit"]]

        return qs

    def handle(self, *args: Any, **options: Any) -> None:
        submissions = list(self.get_submissions(**options))
        total = len(submissions)

        if total == 0:
            self.stdout.write(self.style.WARNING("No submissions to enrich"))
            return

        self.stdout.write(self.style.SUCCESS(f"\nEnriching {total} submission(s)\n"))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("[DRY RUN]\n"))
            for sub in submissions:
                self.stdout.write(f"  Would enrich: {sub.agent_name} ({sub.agent_website})")
            return

        service = EnrichmentService()
        succeeded = 0
        failed = 0
        delay = options["delay"]

        for i, submission in enumerate(submissions, 1):
            self.stdout.write(f"[{i}/{total}] {submission.agent_name}")
            self.stdout.write(f"  URL: {submission.agent_website}")

            try:
                service.enrich_submission(submission)
                if submission.enrichment_data:
                    self.stdout.write(self.style.SUCCESS("  ✓ Enriched"))
                    succeeded += 1
                else:
                    self.stdout.write(self.style.ERROR("  ✗ No data extracted"))
                    failed += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))
                failed += 1
                logger.exception(f"Failed to enrich submission {submission.id}")

            if i < total and delay > 0:
                time.sleep(delay)

        self.stdout.write(f"\n{'=' * 40}")
        self.stdout.write(self.style.SUCCESS(f"Done: {succeeded} succeeded, {failed} failed"))

