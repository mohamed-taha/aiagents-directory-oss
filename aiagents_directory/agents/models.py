from datetime import datetime, timedelta
from typing import Any
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone

from aiagents_directory.agents.constants import AgentStatus, PricingModel, Industry


class Category(models.Model):
    name: str = models.CharField(max_length=100, unique=True)
    slug: str = models.SlugField(max_length=100, unique=True, blank=True)
    description: str = models.TextField(blank=True)
    order: int = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Order in which items appear (starting from 1, lower numbers first)"
    )
    
    class Meta:
        verbose_name_plural = "categories"
        ordering = ["order", "name"]
    
    def __str__(self) -> str:
        return self.name
    
    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


def get_logo_path(instance: "Agent", filename: str) -> str:
    """Generate a path for agent logos with agent slug in filename."""
    ext = Path(filename).suffix
    return f"agents/logos/{instance.slug}{ext}"

def get_screenshot_path(instance: "Screenshot", filename: str) -> str:
    """Generate a path for agent screenshots with agent slug and index."""
    ext = Path(filename).suffix
    # Get count of existing screenshots for this agent to use as index
    count = instance.agent.screenshots.count()
    return f"agents/screenshots/{instance.agent.slug}_{count + 1}{ext}"


def get_submission_logo_path(instance: "AgentSubmission", filename: str) -> str:
    """Generate a path for submission logos."""
    ext = Path(filename).suffix
    return f"submissions/logos/{instance.pk}{ext}"


def get_submission_screenshot_path(instance: "AgentSubmission", filename: str) -> str:
    """Generate a path for submission screenshots."""
    ext = Path(filename).suffix
    return f"submissions/screenshots/{instance.pk}{ext}"


class Feature(models.Model):
    name: str = models.CharField(max_length=200)
    agent = models.ForeignKey(
        'Agent',
        on_delete=models.CASCADE,
        related_name='feature_set'
    )

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ['name']


class UseCase(models.Model):
    name: str = models.CharField(max_length=200)
    agent = models.ForeignKey(
        'Agent',
        on_delete=models.CASCADE,
        related_name='use_case_set'
    )

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ['name']


class Agent(models.Model):
    name: str = models.CharField(max_length=200, unique=True)
    slug: str = models.SlugField(max_length=200, unique=True, blank=True)
    short_description: str = models.CharField(
        max_length=250,
        help_text="A brief one-line description for the card view"
    )
    description: str = models.TextField(
        help_text="Full description for the detail page"
    )
    website: str = models.URLField(
        max_length=255,
        unique=True,
        help_text="The official website URL of the AI agent"
    )
    logo: str = models.ImageField(
        upload_to=get_logo_path,
        default='agents/logos/default-logo.png'
    )
    categories = models.ManyToManyField('Category', related_name='agents')
    order: int = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text="Order in which items appear (starting from 1, lower numbers first)"
    )
    featured: bool = models.BooleanField(
        default=False,
        help_text="Whether this agent should be highlighted as featured"
    )
    is_open_source: bool | None = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether this agent is open source (None = Unknown, True = Yes, False = No)"
    )
    pricing_model: str = models.CharField(
        max_length=20,
        choices=PricingModel.choices,
        default=PricingModel.UNKNOWN
    )
    industry: str = models.CharField(
        max_length=50,
        choices=Industry.choices,
        default=Industry.UNKNOWN,
        help_text="Primary industry or sector this agent serves"
    )
    twitter_url: str = models.URLField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Twitter/X profile URL"
    )
    linkedin_url: str = models.URLField(
        max_length=255,
        null=True,
        blank=True,
        help_text="LinkedIn profile/company URL"
    )
    demo_video_url: str = models.URLField(
        max_length=255,
        null=True,
        blank=True,
        help_text="YouTube, Loom, or Vimeo video URL"
    )
    status: str = models.CharField(
        max_length=20,
        choices=AgentStatus.choices,
        default=AgentStatus.PUBLISHED,
        help_text="Agent visibility status"
    )

    created_at: datetime = models.DateTimeField(auto_now_add=True)
    updated_at: datetime = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-featured", "order", "name"]
    
    def __str__(self) -> str:
        return self.name
    
    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def get_absolute_url(self) -> str:
        """Return the URL for the agent detail page (enables 'View on site' in admin)."""
        from django.urls import reverse
        return reverse("agent_detail", kwargs={"slug": self.slug})

    def get_features_list(self) -> list[str]:
        """Return features as a list of strings."""
        return [f.name for f in self.feature_set.all()]
    
    def get_use_cases_list(self) -> list[str]:
        """Return use cases as a list of strings."""
        return [uc.name for uc in self.use_case_set.all()]

    def get_video_embed_url(self) -> str | None:
        """
        Extract embed URL from demo video URL for YouTube, Vimeo, or Loom.
        Returns None if URL is invalid or not supported.
        """
        if not self.demo_video_url:
            return None
            
        parsed_url = urlparse(self.demo_video_url)
        
        # YouTube
        if 'youtube.com' in parsed_url.netloc or 'youtu.be' in parsed_url.netloc:
            video_id = None
            if 'youtube.com' in parsed_url.netloc:
                # Handle youtube.com/watch?v=VIDEO_ID
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
                # Also handle youtube.com/embed/VIDEO_ID
                if not video_id and '/embed/' in parsed_url.path:
                    video_id = parsed_url.path.split('/embed/')[-1].split('/')[0]
            else:  # youtu.be/VIDEO_ID
                video_id = parsed_url.path.lstrip('/').split('/')[0].split('?')[0]
            
            if video_id:
                # Use youtube-nocookie.com for better privacy and fewer embed restrictions
                return f"https://www.youtube-nocookie.com/embed/{video_id}"
        
        # Vimeo
        elif 'vimeo.com' in parsed_url.netloc:
            video_id = parsed_url.path.split('/')[-1]
            if video_id.isdigit():
                return f"https://player.vimeo.com/video/{video_id}"
        
        # Loom
        elif 'loom.com' in parsed_url.netloc:
            if '/share/' in parsed_url.path:
                video_id = parsed_url.path.split('/')[-1]
                return f"https://www.loom.com/embed/{video_id}"
        
        return None

    def is_new(self, days: int = 30) -> bool:
        """
        Check if agent was created within the specified number of days.
        
        Args:
            days: Number of days to consider as "new" (default: 30 days)
            
        Returns:
            True if agent was created within the specified days, False otherwise
        """
        if not self.created_at:
            return False
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.created_at >= cutoff_date
    
    def get_similar_agents(self, limit: int = 3) -> models.QuerySet["Agent"]:
        """
        Find similar agents based on shared categories and industry.
        Returns a queryset of agents ordered by relevance (number of matching categories).
        """
        from django.db.models import Count, Q

        # Get all categories of current agent
        categories = self.categories.all()

        similar_agents = Agent.objects.exclude(id=self.id).filter(
            status=AgentStatus.PUBLISHED  # Only published agents
        ).filter(
            Q(categories__in=categories) |  # Agents sharing any category
            Q(industry=self.industry)       # Agents in same industry
        ).distinct().annotate(
            matching_categories=Count(
                'categories',
                filter=Q(categories__in=categories)
            )
        ).order_by(
            '-matching_categories',  # Most matching categories first
            '-featured',            # Featured agents get priority
            'order',               # Then by custom order
            'name'                 # Finally alphabetically
        )[:limit]

        return similar_agents

    def get_meta_description(self) -> str:
        """
        Generate SEO-optimized meta description (target 150-160 chars).
        Combines name, categories, short_description, and pricing for richer context.
        """
        parts = [self.name]

        # Add category context
        categories = list(self.categories.all()[:2])
        if categories:
            cat_names = " & ".join(c.name for c in categories)
            parts.append(f"is a {cat_names} AI agent")
        else:
            parts.append("is an AI agent")

        # Add the short description
        if self.short_description:
            desc = self.short_description.strip().rstrip(".")
            desc_lower = desc.lower()
            # Only prepend "that" if description doesn't already flow naturally
            if not desc_lower.startswith(("that ", "which ", "for ", "to ")):
                # Only lowercase first char if it's not an acronym (check first 2 chars)
                # Acronym patterns: "AI", "AI-powered", "LLM", etc.
                is_acronym = len(desc) >= 2 and desc[0].isupper() and desc[1].isupper()
                if not is_acronym and desc[0].isupper():
                    desc = desc[0].lower() + desc[1:]
                desc = "that " + desc
            parts.append(desc)

        # Add pricing if known and useful
        pricing_display = {
            "FREE": "Free",
            "FREEMIUM": "Freemium",
            "PAID": "Paid",
            "OPEN_SOURCE": "Open source",
        }
        if self.pricing_model in pricing_display:
            parts.append(f"({pricing_display[self.pricing_model]})")

        description = " ".join(parts) + "."

        # Truncate intelligently if too long (max 160 chars)
        if len(description) > 160:
            description = description[:157].rsplit(" ", 1)[0] + "..."

        return description


class Screenshot(models.Model):
    agent: Agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name='screenshots'
    )
    image = models.ImageField(upload_to=get_screenshot_path)
    is_primary: bool = models.BooleanField(default=False)
    caption: str = models.CharField(max_length=200, blank=True)
    
    class Meta:
        ordering = ["-is_primary", "id"]
    
    def __str__(self) -> str:
        return f"{self.agent.name} - {'Primary' if self.is_primary else 'Secondary'}"
    
    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.is_primary:
            # Set all other screenshots of this agent to not primary
            Screenshot.objects.filter(agent=self.agent).update(is_primary=False)
        super().save(*args, **kwargs)
    
    def clean(self) -> None:
        if not self.is_primary and not Screenshot.objects.filter(agent=self.agent, is_primary=True).exists():
            raise ValidationError("At least one screenshot must be marked as primary.")


class SubmissionStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Review'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class SubmissionSource(models.TextChoices):
    FORM = 'FORM', 'Submitted via Form'
    AUTO = 'AUTO', 'Automated Sourcing'


class AgentSubmission(models.Model):
    """Tracks agent submissions from users before they become published agents."""
    
    # Submitter information (optional for AUTO source)
    email: str | None = models.EmailField(
        blank=True,
        null=True,
        help_text="Email of the person submitting the agent (required for FORM, optional for AUTO)"
    )
    
    # Agent data as submitted
    agent_name: str = models.CharField(max_length=200, help_text="Name of the agent being submitted")
    agent_website: str = models.URLField(max_length=255, help_text="Website URL of the agent")
    agent_description: str = models.TextField(help_text="Description of the agent")
    
    # Source tracking
    source: str = models.CharField(
        max_length=20,
        choices=SubmissionSource.choices,
        default=SubmissionSource.FORM,
        help_text="How this submission entered the system"
    )
    
    # Linked agent (null until approved and agent created)
    agent = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submissions',
        help_text="The agent record created from this submission (if approved)"
    )
    
    # Review workflow
    status: str = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.PENDING,
        help_text="Current status of the submission"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_submissions',
        help_text="Admin user who reviewed this submission"
    )
    reviewer_notes: str = models.TextField(
        blank=True,
        help_text="Internal notes from the reviewer"
    )
    ai_review_result = models.JSONField(
        null=True,
        blank=True,
        help_text="Results from AI review (ReviewResult as JSON)"
    )
    
    enrichment_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Enrichment data from Firecrawl scraping (URLs and extracted content)"
    )
    
    # Downloaded media (stored immediately during enrichment to avoid URL expiration)
    logo = models.ImageField(
        upload_to=get_submission_logo_path,
        null=True,
        blank=True,
        help_text="Downloaded logo from enrichment (Firecrawl URLs expire in 24h)"
    )
    screenshot = models.ImageField(
        upload_to=get_submission_screenshot_path,
        null=True,
        blank=True,
        help_text="Downloaded screenshot from enrichment (Firecrawl URLs expire in 24h)"
    )
    
    # Review flags
    needs_manual_review: bool = models.BooleanField(
        default=False,
        help_text="Flagged for manual review (low AI confidence or edge case)"
    )
    
    # Timestamps
    submitted_at: datetime = models.DateTimeField(auto_now_add=True)
    reviewed_at: datetime | None = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = "Agent Submission"
        verbose_name_plural = "Agent Submissions"
    
    def __str__(self) -> str:
        identifier = self.email or self.source
        return f"{self.agent_name} - {identifier} ({self.get_status_display()})"
