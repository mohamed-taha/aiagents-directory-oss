"""
News fetching service using Firecrawl's search API.

Fetches AI agent news articles with dates using the sources=["news"] parameter.
"""

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from firecrawl import Firecrawl

from .models import NewsArticle, NewsFetchRun

logger = logging.getLogger(__name__)

# Default news-focused search queries
DEFAULT_NEWS_QUERIES = [
    "ai agents news",
    "ai agent startup news",
    "ai agent funding news",
    "autonomous ai agent news",
]


def parse_relative_date(date_str: str) -> datetime:
    """
    Convert relative date strings to absolute datetime.

    Handles formats like:
    - "3 hours ago"
    - "1 day ago"
    - "2 days ago"
    - "1 week ago"
    - "3 weeks ago"
    - "1 month ago"

    Falls back to current time if unparseable.
    """
    if not date_str:
        return timezone.now()

    date_str = date_str.lower().strip()
    now = timezone.now()

    # Pattern: "X units ago"
    match = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", date_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)

        if unit == "second":
            return now - timedelta(seconds=value)
        elif unit == "minute":
            return now - timedelta(minutes=value)
        elif unit == "hour":
            return now - timedelta(hours=value)
        elif unit == "day":
            return now - timedelta(days=value)
        elif unit == "week":
            return now - timedelta(weeks=value)
        elif unit == "month":
            return now - timedelta(days=value * 30)  # Approximate
        elif unit == "year":
            return now - timedelta(days=value * 365)  # Approximate

    # Try parsing as ISO date
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass

    logger.warning(f"Could not parse date: {date_str}, using current time")
    return now


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


class NewsFetchService:
    """
    Service for fetching AI agent news using Firecrawl.

    Usage:
        service = NewsFetchService()
        run = service.fetch(tbs="qdr:d")  # Past day
    """

    def __init__(
        self,
        queries: list[str] | None = None,
        results_per_query: int = 10,
    ):
        """
        Initialize the news fetch service.

        Args:
            queries: List of search queries (defaults to DEFAULT_NEWS_QUERIES)
            results_per_query: Number of results per query (default: 10)
        """
        self.queries = queries or DEFAULT_NEWS_QUERIES
        self.results_per_query = results_per_query
        self._client: Firecrawl | None = None

    @property
    def client(self) -> Firecrawl:
        """Lazy-load the Firecrawl client."""
        if self._client is None:
            api_key = getattr(settings, "FIRECRAWL_API_KEY", None)
            if not api_key:
                raise ValueError("FIRECRAWL_API_KEY not configured in settings")
            self._client = Firecrawl(api_key=api_key)
        return self._client

    def fetch(
        self,
        tbs: str = "qdr:d",
        dry_run: bool = False,
    ) -> NewsFetchRun:
        """
        Fetch news articles from Firecrawl.

        Args:
            tbs: Time-based search filter (qdr:h, qdr:d, qdr:w, qdr:m)
            dry_run: If True, don't save articles to database

        Returns:
            NewsFetchRun with statistics
        """
        run = NewsFetchRun.objects.create(
            queries_used=self.queries,
            tbs_filter=tbs,
        )

        try:
            articles_found = 0
            articles_created = 0
            articles_skipped = 0
            seen_urls: set[str] = set()

            for query in self.queries:
                logger.info(f"Fetching news for query: {query}")

                try:
                    response = self.client.search(
                        query=query,
                        limit=self.results_per_query,
                        tbs=tbs,
                        sources=["news"],  # Required for news with dates
                    )

                    news_results = getattr(response, "news", None) or []
                    articles_found += len(news_results)

                    for article in news_results:
                        # Convert to dict
                        if hasattr(article, "model_dump"):
                            a = article.model_dump()
                        elif isinstance(article, dict):
                            a = article
                        else:
                            a = article.__dict__

                        url = a.get("url", "")
                        if not url:
                            continue

                        # Normalize URL for deduplication
                        normalized_url = url.lower().rstrip("/")
                        if normalized_url in seen_urls:
                            articles_skipped += 1
                            continue
                        seen_urls.add(normalized_url)

                        if dry_run:
                            logger.info(f"[DRY RUN] Would create: {a.get('title', '')[:50]}")
                            continue

                        # Create article
                        created = self._create_article(
                            title=a.get("title", ""),
                            summary=a.get("snippet", ""),
                            url=url,
                            date_str=a.get("date", ""),
                            search_query=query,
                        )

                        if created:
                            articles_created += 1
                        else:
                            articles_skipped += 1

                except Exception as e:
                    logger.error(f"Error fetching news for query '{query}': {e}")
                    continue

            run.articles_found = articles_found
            run.articles_created = articles_created
            run.articles_skipped = articles_skipped
            run.mark_complete(success=True)

            logger.info(
                f"News fetch complete: {articles_found} found, "
                f"{articles_created} created, {articles_skipped} skipped"
            )

        except Exception as e:
            logger.error(f"News fetch failed: {e}", exc_info=True)
            run.mark_complete(success=False, error=str(e))

        return run

    def _create_article(
        self,
        title: str,
        summary: str,
        url: str,
        date_str: str,
        search_query: str,
    ) -> bool:
        """
        Create a NewsArticle if it doesn't already exist.

        Returns True if created, False if skipped (duplicate).
        """
        if not title or not url:
            return False

        # Parse the relative date
        published_at = parse_relative_date(date_str)
        source_domain = extract_domain(url)

        try:
            NewsArticle.objects.create(
                title=title[:500],
                summary=summary[:2000] if summary else "",
                url=url[:2000],
                source_domain=source_domain,
                published_at=published_at,
                search_query=search_query,
            )
            logger.debug(f"Created article: {title[:50]}")
            return True

        except IntegrityError:
            # Duplicate URL
            logger.debug(f"Skipped duplicate: {url[:50]}")
            return False

        except Exception as e:
            logger.error(f"Error creating article: {e}")
            return False
