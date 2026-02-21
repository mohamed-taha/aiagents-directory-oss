from django.contrib import admin

from .models import NewsArticle, NewsFetchRun


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "source_domain", "published_at", "scraped_at"]
    list_filter = ["source_domain", "published_at"]
    search_fields = ["title", "summary", "url"]
    readonly_fields = ["scraped_at"]
    date_hierarchy = "published_at"
    ordering = ["-published_at"]


@admin.register(NewsFetchRun)
class NewsFetchRunAdmin(admin.ModelAdmin):
    list_display = [
        "started_at",
        "success",
        "articles_found",
        "articles_created",
        "articles_skipped",
        "tbs_filter",
    ]
    list_filter = ["success", "started_at"]
    readonly_fields = [
        "started_at",
        "completed_at",
        "articles_found",
        "articles_created",
        "articles_skipped",
        "queries_used",
    ]
