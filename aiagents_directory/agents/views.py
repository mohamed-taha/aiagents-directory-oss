from typing import Any, Dict
from itertools import chain
import random

from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView
from django.db.models import QuerySet, Q, Count, F, Value, Case, When, IntegerField
from django.db.models.functions import Mod
from django.urls import reverse_lazy
from aiagents_directory.agents.models import Agent, Category, AgentSubmission
from aiagents_directory.agents.constants import AgentStatus
from aiagents_directory.agents.forms import AgentSubmissionForm
from math import ceil
from django.http import Http404
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage


class HomePageView(ListView):
    template_name = "agents/home.html"
    context_object_name = "agents"
    
    def get_queryset(self) -> QuerySet[Agent]:
        queryset = Agent.objects.filter(status=AgentStatus.PUBLISHED).prefetch_related('categories', 'screenshots')
        
        # Handle search
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(short_description__icontains=search_query) |
                Q(description__icontains=search_query)
            )
            # Keep deterministic ordering for search results
        else:
            # Use session-based seed for database-level randomization
            session_key = 'agent_random_seed'
            if session_key not in self.request.session:
                self.request.session[session_key] = random.randint(1, 1000000)
            
            seed = self.request.session[session_key]
            
            # Featured agents first (ordered by order, name)
            # Non-featured agents randomized using database with seed
            # Use deterministic hash: (id * seed) % large_number for consistent ordering
            queryset = queryset.annotate(
                random_order=Mod(F('id') * Value(seed), Value(1000000)),
                # Sort key: for featured use 'order', for non-featured use random_order
                sort_key=Case(
                    When(featured=True, then=F('order')),
                    default=F('random_order'),
                    output_field=IntegerField()
                )
            ).order_by('-featured', 'sort_key', 'name')
            
        return queryset[:24]  # Show first 24 agents on homepage
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        
        # Get all categories with their agent counts
        context['categories'] = Category.objects.annotate(
            agent_count=Count('agents')
        ).filter(agent_count__gt=0).order_by('order', '-agent_count')
        
        context['total_agents_count'] = Agent.objects.filter(status=AgentStatus.PUBLISHED).count()
        context['search_query'] = self.request.GET.get('search', '')
        
        return context

class AgentDetailView(DetailView):
    model = Agent
    template_name = 'agents/agent_detail.html'
    context_object_name = 'agent'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get similar agents
        context['similar_agents'] = self.object.get_similar_agents(limit=3)
        context['meta_description'] = self.object.short_description
        
        # Add is_open_source to context for template
        context['is_open_source'] = self.object.is_open_source
        
        return context

class AgentListView(ListView):
    template_name = "agents/agent_list.html"
    context_object_name = "agents"
    paginate_by = 24

    def get_queryset(self) -> QuerySet[Agent]:
        queryset = Agent.objects.filter(status=AgentStatus.PUBLISHED).prefetch_related(
            'categories',
            'screenshots'
        )
        
        # Handle search
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(short_description__icontains=search_query) |
                Q(description__icontains=search_query)
            )
            # Keep deterministic ordering for search results
        else:
            # Use session-based seed for database-level randomization
            session_key = 'agent_random_seed'
            if session_key not in self.request.session:
                self.request.session[session_key] = random.randint(1, 1000000)
            
            seed = self.request.session[session_key]
            
            # Featured agents first (ordered by order, name)
            # Non-featured agents randomized using database with seed
            # Use deterministic hash: (id * seed) % large_number for consistent ordering
            queryset = queryset.annotate(
                random_order=Mod(F('id') * Value(seed), Value(1000000)),
                # Sort key: for featured use 'order', for non-featured use random_order
                sort_key=Case(
                    When(featured=True, then=F('order')),
                    default=F('random_order'),
                    output_field=IntegerField()
                )
            ).order_by('-featured', 'sort_key', 'name')
            
        return queryset
    
    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            # If page is out of range, redirect to last page
            querydict = request.GET.copy()
            total_pages = ceil(self.get_queryset().count() / self.paginate_by)
            if total_pages > 0:
                querydict['page'] = total_pages
                return redirect(f"{request.path}?{querydict.urlencode()}")
            return super().get(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        
        # Base URL without query parameters
        base_url = f"{self.request.scheme}://{self.request.get_host()}{self.request.path}"
        
        # Get current query parameters
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        base_params = params.urlencode()
        
        # Build pagination URLs
        if context['page_obj'].has_previous():
            prev_params = f"{base_params}&page={context['page_obj'].previous_page_number()}" if base_params else f"page={context['page_obj'].previous_page_number()}"
            context['prev_page_url'] = f"{base_url}?{prev_params}"
            
        if context['page_obj'].has_next():
            next_params = f"{base_params}&page={context['page_obj'].next_page_number()}" if base_params else f"page={context['page_obj'].next_page_number()}"
            context['next_page_url'] = f"{base_url}?{next_params}"
        
        context['categories'] = Category.objects.annotate(
            agent_count=Count('agents')
        ).filter(agent_count__gt=0).order_by('order', '-agent_count')
        context['search_query'] = self.request.GET.get('search', '')
        context['total_agents_count'] = Agent.objects.filter(status=AgentStatus.PUBLISHED).count()
        return context


class CategoryDetailView(DetailView):
    model = Category
    template_name = "agents/category_detail.html"
    context_object_name = "category"
    slug_url_kwarg = 'slug'
    query_pk_and_slug = False
    paginate_by = 48
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        
        # Get search query
        search_query = self.request.GET.get('search', '')
        
        # Get agents for this category
        agents = self.object.agents.filter(status=AgentStatus.PUBLISHED).prefetch_related('categories', 'screenshots')
        if search_query:
            agents = agents.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(short_description__icontains=search_query)
            )
            # Keep deterministic ordering for search results
        else:
            # Use session-based seed for database-level randomization
            session_key = 'agent_random_seed'
            if session_key not in self.request.session:
                self.request.session[session_key] = random.randint(1, 1000000)
            
            seed = self.request.session[session_key]
            
            # Featured agents first (ordered by order, name)
            # Non-featured agents randomized using database with seed
            # Use deterministic hash: (id * seed) % large_number for consistent ordering
            agents = agents.annotate(
                random_order=Mod(F('id') * Value(seed), Value(1000000)),
                # Sort key: for featured use 'order', for non-featured use random_order
                sort_key=Case(
                    When(featured=True, then=F('order')),
                    default=F('random_order'),
                    output_field=IntegerField()
                )
            ).order_by('-featured', 'sort_key', 'name')
        
        # Paginate
        paginator = Paginator(agents, self.paginate_by)
        page = self.request.GET.get('page')
        try:
            agents = paginator.page(page)
        except PageNotAnInteger:
            agents = paginator.page(1)
        except EmptyPage:
            agents = paginator.page(paginator.num_pages)
            
        # Base URL without query parameters
        base_url = f"{self.request.scheme}://{self.request.get_host()}{self.request.path}"
        
        # Get current query parameters
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        base_params = params.urlencode()
        
        # Build pagination URLs
        if agents.has_previous():
            prev_params = f"{base_params}&page={agents.previous_page_number()}" if base_params else f"page={agents.previous_page_number()}"
            context['prev_page_url'] = f"{base_url}?{prev_params}"
            
        if agents.has_next():
            next_params = f"{base_params}&page={agents.next_page_number()}" if base_params else f"page={agents.next_page_number()}"
            context['next_page_url'] = f"{base_url}?{next_params}"
            
        # Get all categories with counts
        categories = Category.objects.annotate(
            agent_count=Count('agents')
        ).filter(agent_count__gt=0).order_by('order', '-agent_count')
            
        context.update({
            'agents': agents,
            'categories': categories,
            'search_query': search_query,
            'total_agents_count': Agent.objects.filter(status=AgentStatus.PUBLISHED).count(),
            'current_category': self.object,
        })
        
        return context


class AgentSubmissionView(CreateView):
    """View for submitting a new agent to the directory."""
    model = AgentSubmission
    form_class = AgentSubmissionForm
    template_name = 'agents/submit.html'
    success_url = reverse_lazy('agent_submission_success')
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['total_agents_count'] = Agent.objects.filter(status=AgentStatus.PUBLISHED).count()
        return context


class AgentSubmissionSuccessView(ListView):
    """Success page after submitting an agent."""
    template_name = 'agents/submit_success.html'
    context_object_name = 'agents'
    
    def get_queryset(self) -> QuerySet[Agent]:
        # Show some featured agents
        return Agent.objects.filter(
            status=AgentStatus.PUBLISHED,
            featured=True
        ).prefetch_related('categories', 'screenshots')[:6]
    
    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['total_agents_count'] = Agent.objects.filter(status=AgentStatus.PUBLISHED).count()
        return context
