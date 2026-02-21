from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class NewsSitemap(Sitemap):
    """Sitemap for news archive pages."""

    changefreq = "daily"
    priority = 0.7

    def items(self):
        return [
            "news_archive",
            "news_today",
            "news_this_week",
            "news_this_month",
        ]

    def location(self, item):
        return reverse(item)
