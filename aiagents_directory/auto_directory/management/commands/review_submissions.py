"""
AI review enriched agent submissions using Pydantic AI.

Usage:
    # Review all enriched submissions (not yet reviewed)
    python manage.py review_submissions

    # Review specific submissions by ID
    python manage.py review_submissions --ids 1 2 3

    # Auto-approve/reject based on AI decision
    python manage.py review_submissions --auto-apply

    # Limit number processed
    python manage.py review_submissions --limit 5
"""

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import QuerySet

from aiagents_directory.agents.models import AgentSubmission, SubmissionStatus
from aiagents_directory.auto_directory.services import ReviewService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "AI review enriched agent submissions"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--ids",
            type=int,
            nargs="+",
            help="Specific submission IDs to review",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of submissions to process",
        )
        parser.add_argument(
            "--auto-apply",
            action="store_true",
            help="Auto-approve/reject based on AI decision (use with caution)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-review even if already reviewed",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def get_submissions(self, **options: Any) -> QuerySet[AgentSubmission]:
        """Build queryset: enriched but not yet reviewed."""
        qs = AgentSubmission.objects.filter(status=SubmissionStatus.PENDING)

        if options["ids"]:
            qs = qs.filter(id__in=options["ids"])
            self.stdout.write(f"Filtering by IDs: {options['ids']}")

        # Must be enriched
        qs = qs.exclude(enrichment_data__isnull=True)

        if not options["force"]:
            # Not yet reviewed
            qs = qs.filter(ai_review_result__isnull=True)

        if options["limit"]:
            qs = qs[: options["limit"]]

        return qs

    def handle(self, *args: Any, **options: Any) -> None:
        submissions = list(self.get_submissions(**options))
        total = len(submissions)

        if total == 0:
            self.stdout.write(self.style.WARNING("No submissions to review"))
            return

        auto_apply = options["auto_apply"]
        mode = "AUTO-APPLY" if auto_apply else "review only"
        self.stdout.write(self.style.SUCCESS(f"\nReviewing {total} submission(s) [{mode}]\n"))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("[DRY RUN]\n"))
            for sub in submissions:
                self.stdout.write(f"  Would review: {sub.agent_name}")
            return

        service = ReviewService()
        results = {"approved": 0, "rejected": 0, "needs_review": 0, "error": 0}

        for i, submission in enumerate(submissions, 1):
            self.stdout.write(f"[{i}/{total}] {submission.agent_name}")

            try:
                # review_submission returns the updated submission
                submission = service.review_submission(submission, auto_apply=auto_apply)
                
                # Get result from the saved ai_review_result field
                review = submission.ai_review_result
                decision = review["decision"]
                confidence = f"{review['confidence']:.0%}"
                results[decision] = results.get(decision, 0) + 1

                style = {
                    "approved": self.style.SUCCESS,
                    "rejected": self.style.ERROR,
                    "needs_review": self.style.WARNING,
                }.get(decision, self.style.NOTICE)

                status_note = ""
                if auto_apply and review.get("auto_applied"):
                    status_note = f" → status={submission.status}"

                self.stdout.write(style(f"  {decision.upper()} ({confidence}){status_note}"))

                if submission.needs_manual_review:
                    self.stdout.write(self.style.WARNING("  ⚠ Flagged for manual review"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {e}"))
                results["error"] += 1
                logger.exception(f"Failed to review submission {submission.id}")

        self.stdout.write(f"\n{'=' * 40}")
        self.stdout.write(
            f"Results: {results['approved']} approved, {results['rejected']} rejected, "
            f"{results['needs_review']} needs_review, {results['error']} errors"
        )

