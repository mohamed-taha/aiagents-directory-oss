from datetime import timedelta

from django.utils import timezone
from django.views.generic import ListView

from .models import NewsArticle


class NewsArchiveView(ListView):
    """Base view for news archive with time filtering."""

    model = NewsArticle
    template_name = "news/news_archive.html"
    context_object_name = "articles"
    paginate_by = 30

    # Override in subclasses
    time_filter = None  # None = all, "today", "week", "month"
    page_title = "AI Agents News"
    time_label = ""  # For dynamic meta description

    def get_queryset(self):
        qs = NewsArticle.objects.all()

        if self.time_filter == "today":
            today = timezone.now().date()
            qs = qs.filter(published_at__date=today)
        elif self.time_filter == "week":
            week_ago = timezone.now() - timedelta(days=7)
            qs = qs.filter(published_at__gte=week_ago)
        elif self.time_filter == "month":
            month_ago = timezone.now() - timedelta(days=30)
            qs = qs.filter(published_at__gte=month_ago)

        return qs.order_by("-published_at")

    def get_meta_description(self, count: int) -> str:
        """Generate dynamic meta description with article count."""
        if self.time_filter == "today":
            return f"{count} AI agent news articles from today. Latest updates on autonomous AI, AI startups, and automation tools."
        elif self.time_filter == "week":
            return f"{count} AI agent news articles from this week. Updates on AI agents, startups, funding, and industry news."
        elif self.time_filter == "month":
            return f"{count} AI agent news articles from this month. Coverage of AI agents, autonomous AI, and automation trends."
        else:
            return f"Browse {count} AI agent news articles. Latest updates on autonomous AI, AI startups, funding, and automation tools."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_count = self.get_queryset().count()

        context["time_filter"] = self.time_filter or "all"
        context["page_title"] = self.page_title
        context["meta_description"] = self.get_meta_description(total_count)
        context["total_count"] = total_count
        return context


class NewsTodayView(NewsArchiveView):
    """Today's AI agent news."""

    time_filter = "today"
    page_title = "Today's AI Agents News"


class NewsThisWeekView(NewsArchiveView):
    """This week's AI agent news."""

    time_filter = "week"
    page_title = "This Week's AI Agents News"


class NewsThisMonthView(NewsArchiveView):
    """This month's AI agent news."""

    time_filter = "month"
    page_title = "This Month's AI Agents News"
