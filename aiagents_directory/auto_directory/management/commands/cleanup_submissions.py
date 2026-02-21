"""
Management command to cleanup existing agent submissions.

This command processes PENDING + AUTO-sourced submissions to:
1. Auto-reject submissions matching blocklist patterns
2. Extract real URLs from aggregator pages (YC, ProductHunt, etc.)
3. Flag uncertain cases for manual review

Usage:
    python manage.py cleanup_submissions                    # Full cleanup
    python manage.py cleanup_submissions --dry-run          # Preview changes
    python manage.py cleanup_submissions --reject-only      # Only reject bad ones
    python manage.py cleanup_submissions --extract-only     # Only extract URLs
"""

import logging
from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Q

from aiagents_directory.agents.models import (
    AgentSubmission,
    SubmissionSource,
    SubmissionStatus,
)
from aiagents_directory.auto_directory.filters import (
    get_block_reason,
    get_url_classification,
    is_aggregator_url,
    is_blocked_url,
)
from aiagents_directory.auto_directory.services.enrichment import EnrichmentService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cleanup existing PENDING + AUTO-sourced submissions"
    
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without making them",
        )
        parser.add_argument(
            "--reject-only",
            action="store_true",
            help="Only reject blocklisted submissions, skip URL extraction",
        )
        parser.add_argument(
            "--extract-only",
            action="store_true",
            help="Only extract URLs from aggregators, skip rejections",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of submissions to process",
        )
    
    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        reject_only = options["reject_only"]
        extract_only = options["extract_only"]
        limit = options.get("limit")
        
        if reject_only and extract_only:
            self.stderr.write(
                self.style.ERROR("Cannot use both --reject-only and --extract-only")
            )
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made\n"))
        
        # Get target submissions: PENDING + AUTO source only
        queryset = AgentSubmission.objects.filter(
            status=SubmissionStatus.PENDING,
            source=SubmissionSource.AUTO,
        )
        
        if limit:
            queryset = queryset[:limit]
        
        total = queryset.count()
        self.stdout.write(f"Found {total} PENDING + AUTO submissions to process\n")
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to process."))
            return
        
        # Initialize counters
        stats = {
            "rejected": 0,
            "extracted": 0,
            "flagged": 0,
            "skipped": 0,
            "errors": 0,
        }
        
        # Initialize enrichment service for URL extraction
        enrichment_service = None
        if not reject_only:
            enrichment_service = EnrichmentService()
        
        # Process each submission
        for submission in queryset:
            try:
                self._process_submission(
                    submission=submission,
                    dry_run=dry_run,
                    reject_only=reject_only,
                    extract_only=extract_only,
                    enrichment_service=enrichment_service,
                    stats=stats,
                )
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(
                        f"Error processing [{submission.id}] {submission.agent_name}: {e}"
                    )
                )
                stats["errors"] += 1
        
        # Print summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CLEANUP SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Total processed: {total}")
        self.stdout.write(f"  Rejected: {stats['rejected']}")
        self.stdout.write(f"  URLs extracted: {stats['extracted']}")
        self.stdout.write(f"  Flagged for review: {stats['flagged']}")
        self.stdout.write(f"  Skipped: {stats['skipped']}")
        self.stdout.write(f"  Errors: {stats['errors']}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - no changes were made"))
    
    def _process_submission(
        self,
        submission: AgentSubmission,
        dry_run: bool,
        reject_only: bool,
        extract_only: bool,
        enrichment_service: EnrichmentService | None,
        stats: dict,
    ) -> None:
        """Process a single submission."""
        url = submission.agent_website
        classification = get_url_classification(url)
        
        # Handle blocked URLs
        if classification == "blocked" and not extract_only:
            reason = get_block_reason(url)
            self.stdout.write(
                f"[REJECT] [{submission.id}] {submission.agent_name[:30]:30s} | "
                f"{url[:50]}... | {reason}"
            )
            
            if not dry_run:
                submission.status = SubmissionStatus.REJECTED
                submission.reviewer_notes = f"Auto-rejected by cleanup: {reason}"
                submission.save(update_fields=["status", "reviewer_notes"])
            
            stats["rejected"] += 1
            return
        
        # Handle aggregator URLs - extract real URL
        if classification == "aggregator" and not reject_only:
            self.stdout.write(
                f"[EXTRACT] [{submission.id}] {submission.agent_name[:30]:30s} | "
                f"{url[:50]}..."
            )
            
            if not dry_run and enrichment_service:
                # Use enrichment service to extract real URL
                old_url = submission.agent_website
                try:
                    # This will extract the real URL and update the submission
                    enrichment_service.enrich_submission(submission)
                    submission.refresh_from_db()
                    
                    if submission.agent_website != old_url:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  -> Extracted: {submission.agent_website[:60]}..."
                            )
                        )
                        stats["extracted"] += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING("  -> Could not extract URL")
                        )
                        # Flag for manual review
                        submission.needs_manual_review = True
                        submission.save(update_fields=["needs_manual_review"])
                        stats["flagged"] += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  -> Extraction failed: {e}")
                    )
                    stats["errors"] += 1
            else:
                stats["extracted"] += 1  # Count as would-be extracted in dry run
            
            return
        
        # Handle GitHub URLs
        if classification == "github":
            self.stdout.write(
                f"[FLAG] [{submission.id}] {submission.agent_name[:30]:30s} | "
                f"GitHub (open source candidate)"
            )
            
            if not dry_run:
                submission.needs_manual_review = True
                if submission.enrichment_data:
                    meta = submission.enrichment_data.get("_sourcing_metadata", {})
                    meta["is_github"] = True
                    meta["potential_open_source"] = True
                    submission.enrichment_data["_sourcing_metadata"] = meta
                    submission.save(update_fields=["needs_manual_review", "enrichment_data"])
                else:
                    submission.save(update_fields=["needs_manual_review"])
            
            stats["flagged"] += 1
            return
        
        # Handle non-root URLs
        if classification == "non_root":
            self.stdout.write(
                f"[FLAG] [{submission.id}] {submission.agent_name[:30]:30s} | "
                f"Non-root URL"
            )
            
            if not dry_run:
                submission.needs_manual_review = True
                submission.save(update_fields=["needs_manual_review"])
            
            stats["flagged"] += 1
            return
        
        # Normal URLs - skip
        stats["skipped"] += 1

