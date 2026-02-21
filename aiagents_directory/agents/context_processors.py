from django.db.models import Count, Q
from .models import Category
from .constants import AgentStatus

def footer_context(request):
    """Global context processor for footer data including categories with their counts."""
    return {
        'footer_categories': Category.objects.annotate(
            agent_count=Count('agents', filter=Q(agents__status=AgentStatus.PUBLISHED))
        ).filter(agent_count__gt=0).order_by('-agent_count')
    }