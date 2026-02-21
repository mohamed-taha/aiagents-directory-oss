from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from aiagents_directory.agents.models import Agent, Category
from aiagents_directory.agents.constants import AgentStatus

class AgentSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Agent.objects.filter(status=AgentStatus.PUBLISHED)

    def location(self, obj):
        return f'/{obj.slug}/'

class CategorySitemap(Sitemap):
    changefreq = "weekly"  # Categories change less frequently
    priority = 0.7

    def items(self):
        return Category.objects.all()

    def location(self, obj):
        return f'/categories/{obj.slug}/'  # Matches our URL pattern

class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return [
            'home',
            'agent_list',
        ]

    def location(self, item):
        return reverse(item)
