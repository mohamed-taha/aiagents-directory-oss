"""
Reject agent submissions.

Usage:
    # Reject all AI-rejected submissions
    python manage.py reject_submissions

    # Reject specific submissions by ID
    python manage.py reject_submissions --ids 1 2 3

    # Reject even without AI review (manual override)
    python manage.py reject_submissions --ids 1 2 3 --skip-review-check
"""

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import QuerySet

from aiagents_directory.agents.models import AgentSubmission, SubmissionStatus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reject agent submissions"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--ids",
            type=int,
            nargs="+",
            help="Specific submission IDs to reject",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of submissions to process",
        )
        parser.add_argument(
            "--skip-review-check",
            action="store_true",
            help="Reject even without AI rejection (manual override)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def get_submissions(self, **options: Any) -> QuerySet[AgentSubmission]:
        """Build queryset: AI-rejected submissions."""
        qs = AgentSubmission.objects.filter(status=SubmissionStatus.PENDING)

        if options["ids"]:
            qs = qs.filter(id__in=options["ids"])
            self.stdout.write(f"Filtering by IDs: {options['ids']}")

        if not options["skip_review_check"]:
            # Only AI-rejected submissions
            qs = qs.filter(ai_review_result__decision="rejected")

        if options["limit"]:
            qs = qs[: options["limit"]]

        return qs

    def handle(self, *args: Any, **options: Any) -> None:
        submissions = list(self.get_submissions(**options))
        total = len(submissions)

        if total == 0:
            self.stdout.write(self.style.WARNING("No submissions to reject"))
            return

        mode = "SKIP REVIEW CHECK" if options["skip_review_check"] else "AI-rejected only"
        self.stdout.write(self.style.SUCCESS(f"\nRejecting {total} submission(s) [{mode}]\n"))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("[DRY RUN]\n"))
            for sub in submissions:
                reason = ""
                if sub.ai_review_result:
                    reason = sub.ai_review_result.get("reasoning", "")[:50]
                    if reason:
                        reason = f" - {reason}..."
                self.stdout.write(f"  Would reject: {sub.agent_name}{reason}")
            return

        rejected = 0

        for i, submission in enumerate(submissions, 1):
            self.stdout.write(f"[{i}/{total}] {submission.agent_name}")

            try:
                submission.status = SubmissionStatus.REJECTED
                submission.save(update_fields=["status"])
                self.stdout.write(self.style.SUCCESS("  ✓ Rejected"))
                rejected += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))
                logger.exception(f"Failed to reject submission {submission.id}")

        self.stdout.write(f"\n{'=' * 40}")
        self.stdout.write(self.style.SUCCESS(f"Done: {rejected} rejected"))

