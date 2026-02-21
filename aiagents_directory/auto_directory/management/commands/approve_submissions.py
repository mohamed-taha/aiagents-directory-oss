"""
Approve agent submissions and create Agent instances.

Usage:
    # Approve all AI-approved submissions
    python manage.py approve_submissions

    # Approve specific submissions by ID
    python manage.py approve_submissions --ids 1 2 3

    # Approve even without AI review (manual override)
    python manage.py approve_submissions --ids 1 2 3 --skip-review-check

    # Limit number processed
    python manage.py approve_submissions --limit 5
"""

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import QuerySet
from django.utils import timezone

from aiagents_directory.agents.models import AgentSubmission, SubmissionStatus
from aiagents_directory.auto_directory.services import DuplicateAgentError, EnrichmentService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Approve submissions and create Agent instances"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--ids",
            type=int,
            nargs="+",
            help="Specific submission IDs to approve",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of submissions to process",
        )
        parser.add_argument(
            "--skip-review-check",
            action="store_true",
            help="Approve even without AI approval (manual override)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def get_submissions(self, **options: Any) -> QuerySet[AgentSubmission]:
        """Build queryset: AI-approved submissions ready to create agents."""
        qs = AgentSubmission.objects.filter(status=SubmissionStatus.PENDING)

        if options["ids"]:
            qs = qs.filter(id__in=options["ids"])
            self.stdout.write(f"Filtering by IDs: {options['ids']}")

        if not options["skip_review_check"]:
            # Only AI-approved submissions
            qs = qs.filter(ai_review_result__decision="approved")

        if options["limit"]:
            qs = qs[: options["limit"]]

        return qs

    def handle(self, *args: Any, **options: Any) -> None:
        submissions = list(self.get_submissions(**options))
        total = len(submissions)

        if total == 0:
            self.stdout.write(self.style.WARNING("No submissions to approve"))
            return

        mode = "SKIP REVIEW CHECK" if options["skip_review_check"] else "AI-approved only"
        self.stdout.write(self.style.SUCCESS(f"\nApproving {total} submission(s) [{mode}]\n"))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("[DRY RUN]\n"))
            for sub in submissions:
                review_info = ""
                if sub.ai_review_result:
                    review_info = f" [AI: {sub.ai_review_result.get('decision', 'unknown')}]"
                self.stdout.write(f"  Would approve: {sub.agent_name}{review_info}")
            return

        service = EnrichmentService()
        succeeded = 0
        rejected_duplicates = 0
        failed = 0

        for i, submission in enumerate(submissions, 1):
            self.stdout.write(f"[{i}/{total}] {submission.agent_name}")

            try:
                agent = service.create_agent_from_submission(submission)
                submission.status = SubmissionStatus.APPROVED
                submission.agent = agent
                submission.reviewed_at = timezone.now()
                submission.save(update_fields=["status", "agent", "reviewed_at"])

                self.stdout.write(self.style.SUCCESS(f"  ✓ Created agent: {agent.slug}"))
                succeeded += 1

            except DuplicateAgentError as e:
                # Auto-reject duplicate
                submission.status = SubmissionStatus.REJECTED
                submission.reviewer_notes = f"Auto-rejected: {e}"
                submission.reviewed_at = timezone.now()
                submission.save(update_fields=["status", "reviewer_notes", "reviewed_at"])
                
                self.stdout.write(self.style.WARNING(f"  ⊘ Rejected (duplicate): {e}"))
                rejected_duplicates += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))
                failed += 1
                logger.exception(f"Failed to approve submission {submission.id}")

        self.stdout.write(f"\n{'=' * 40}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {succeeded} created, {rejected_duplicates} rejected (duplicates), {failed} failed"
            )
        )

