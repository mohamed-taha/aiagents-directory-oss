"""
Management command to manually request indexing for URLs.

Usage:
    python manage.py request_indexing /ai-agents-news/
    python manage.py request_indexing /chatgpt/
    python manage.py request_indexing --news-pages
    python manage.py request_indexing --recent-agents --days=7
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from aiagents_directory.utils.indexing import request_indexing


class Command(BaseCommand):
    help = "Request search engine indexing for URLs"

    def add_arguments(self, parser):
        parser.add_argument(
            "urls",
            nargs="*",
            help="URL paths to index (e.g., /ai-agents-news/)",
        )
        parser.add_argument(
            "--news-pages",
            action="store_true",
            help="Index all news archive pages",
        )
        parser.add_argument(
            "--recent-agents",
            action="store_true",
            help="Index recently added agents",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Days to look back for --recent-agents (default: 7)",
        )

    def handle(self, *args, **options):
        urls_to_index = []

        # Specific URLs
        if options["urls"]:
            urls_to_index.extend(options["urls"])

        # News pages
        if options["news_pages"]:
            urls_to_index.extend([
                "/ai-agents-news/",
                "/ai-agents-news/today/",
                "/ai-agents-news/this-week/",
                "/ai-agents-news/this-month/",
            ])

        # Recent agents
        if options["recent_agents"]:
            from aiagents_directory.agents.models import Agent
            from aiagents_directory.agents.constants import AgentStatus

            days = options["days"]
            cutoff = timezone.now() - timedelta(days=days)

            agents = Agent.objects.filter(
                status=AgentStatus.PUBLISHED,
                created_at__gte=cutoff,
            )

            for agent in agents:
                urls_to_index.append(f"/{agent.slug}/")

        if not urls_to_index:
            self.stdout.write(self.style.WARNING("No URLs specified. Use --help for options."))
            return

        # Deduplicate
        urls_to_index = list(set(urls_to_index))

        self.stdout.write(f"Requesting indexing for {len(urls_to_index)} URLs...")

        for url in urls_to_index:
            result = request_indexing(url)
            status = "✓" if (result["google"] or result["bing"]) else "✗"
            self.stdout.write(f"  {status} {url} (Google: {result['google']}, Bing: {result['bing']})")

        self.stdout.write(self.style.SUCCESS("Done."))
