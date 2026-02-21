"""
Management command to fetch AI agent news.

Usage:
    python manage.py fetch_news              # Past 24 hours (default)
    python manage.py fetch_news --tbs=qdr:w  # Past week
    python manage.py fetch_news --dry-run    # Preview only
"""

from django.core.management.base import BaseCommand
from django.db.models.signals import post_save

from aiagents_directory.news.models import NewsArticle
from aiagents_directory.news.services import NewsFetchService
from aiagents_directory.news.signals import index_news_pages
from aiagents_directory.utils.indexing import request_indexing


class Command(BaseCommand):
    help = "Fetch AI agent news articles from Firecrawl"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tbs",
            type=str,
            default="qdr:d",
            help="Time-based search filter: qdr:h (hour), qdr:d (day), qdr:w (week), qdr:m (month)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Results per query (default: 10)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview results without saving to database",
        )

    def handle(self, *args, **options):
        tbs = options["tbs"]
        limit = options["limit"]
        dry_run = options["dry_run"]

        self.stdout.write(f"Fetching news with tbs={tbs}, limit={limit}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no articles will be saved"))

        # Disconnect the signal to prevent indexing after each article save
        post_save.disconnect(index_news_pages, sender=NewsArticle)

        try:
            service = NewsFetchService(results_per_query=limit)
            run = service.fetch(tbs=tbs, dry_run=dry_run)

            if run.success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Success: {run.articles_found} found, "
                        f"{run.articles_created} created, "
                        f"{run.articles_skipped} skipped"
                    )
                )

                # Submit all 4 listing pages for indexing after command finishes
                if not dry_run and run.articles_created > 0:
                    self.stdout.write("Submitting news listing pages for indexing...")
                    news_pages = [
                        "/ai-agents-news/",
                        "/ai-agents-news/today/",
                        "/ai-agents-news/this-week/",
                        "/ai-agents-news/this-month/",
                    ]
                    for page in news_pages:
                        result = request_indexing(page)
                        self.stdout.write(
                            f"  {page}: Google={result['google']}, Bing={result['bing']}"
                        )
            else:
                self.stdout.write(
                    self.style.ERROR(f"Failed: {run.error_message}")
                )
        finally:
            # Reconnect the signal
            post_save.connect(index_news_pages, sender=NewsArticle)
