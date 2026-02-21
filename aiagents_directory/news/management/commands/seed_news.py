"""
Management command to seed historical news data.

Usage:
    python manage.py seed_news               # Past 2 months (default)
    python manage.py seed_news --months=3    # Past 3 months
"""

from django.core.management.base import BaseCommand

from aiagents_directory.news.services import NewsFetchService


class Command(BaseCommand):
    help = "Seed historical AI agent news (backfill)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=int,
            default=2,
            help="Number of months to fetch (default: 2)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Results per query (default: 20)",
        )

    def handle(self, *args, **options):
        months = options["months"]
        limit = options["limit"]

        self.stdout.write(f"Seeding news for past {months} months")

        service = NewsFetchService(results_per_query=limit)

        # Use month filter for historical data
        tbs = "qdr:m" if months == 1 else f"qdr:y"  # Firecrawl doesn't support multi-month directly

        # For proper multi-month seeding, we'd need custom date ranges
        # For now, use qdr:m for 1-2 months, qdr:y for longer
        if months <= 2:
            tbs = "qdr:m"
        else:
            # Use custom date range format: cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=months * 30)
            tbs = f"cdr:1,cd_min:{start_date.month}/{start_date.day}/{start_date.year},cd_max:{end_date.month}/{end_date.day}/{end_date.year}"

        self.stdout.write(f"Using time filter: {tbs}")

        run = service.fetch(tbs=tbs)

        if run.success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeding complete: {run.articles_found} found, "
                    f"{run.articles_created} created, "
                    f"{run.articles_skipped} skipped"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"Seeding failed: {run.error_message}")
            )
