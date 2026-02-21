from django.urls import path

from aiagents_directory.agents.views import (
    HomePageView,
    AgentListView,
    AgentDetailView,
    CategoryDetailView,
    AgentSubmissionView,
    AgentSubmissionSuccessView,
)


urlpatterns = [
    # Home page
    path('', HomePageView.as_view(), name='home'),
    
    # Agents listing
    path('agents/', AgentListView.as_view(), name='agent_list'),
    
    # Agent submission
    path('submit/', AgentSubmissionView.as_view(), name='agent_submission'),
    path('submit/success/', AgentSubmissionSuccessView.as_view(), name='agent_submission_success'),
    
    # Category listing (explicit path)
    path('categories/<slug:slug>/', CategoryDetailView.as_view(), name='category_detail'),
    
    # Agent detail (catch-all for agent slugs)
    path('<slug:slug>/', AgentDetailView.as_view(), name='agent_detail'),
]
