from django.urls import path

from .views import (
    NewsArchiveView,
    NewsThisMonthView,
    NewsThisWeekView,
    NewsTodayView,
)

urlpatterns = [
    path("ai-agents-news/", NewsArchiveView.as_view(), name="news_archive"),
    path("ai-agents-news/today/", NewsTodayView.as_view(), name="news_today"),
    path("ai-agents-news/this-week/", NewsThisWeekView.as_view(), name="news_this_week"),
    path("ai-agents-news/this-month/", NewsThisMonthView.as_view(), name="news_this_month"),
]
