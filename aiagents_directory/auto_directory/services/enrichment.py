"""
Agent enrichment service.

This module provides the EnrichmentService class for enriching agent data
by scraping their websites using Firecrawl's API.

Features:
- Scraping websites using Firecrawl
- Aggregator URL extraction (YC, ProductHunt, etc.)
- Name verification and correction
- Canonical URL extraction
"""

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from firecrawl import Firecrawl

from aiagents_directory.agents.models import (
    Agent,
    AgentSubmission,
    Category,
    Feature,
    Screenshot,
    UseCase,
)
from aiagents_directory.auto_directory.filters import (
    AGGREGATOR_URL_EXTRACTION_PROMPT,
    get_aggregator_extraction_schema,
    is_aggregator_url,
)
from aiagents_directory.auto_directory.models import EnrichmentLog
from aiagents_directory.auto_directory.schemas import (
    AgentEnrichmentSchema,
    EnrichmentResult,
)


logger = logging.getLogger(__name__)


# Fields that should never be enriched (excluded from enrichment)
EXCLUDED_FIELDS = frozenset({
    "name",
    "slug", 
    "order",
    "featured",
    "website",
    "status",
    "created_at",
    "updated_at",
})

# All enrichable fields
ENRICHABLE_FIELDS = frozenset({
    "short_description",
    "description",
    "features",
    "use_cases",
    "pricing_model",
    "category",
    "is_open_source",
    "industry",
    "twitter_url",
    "linkedin_url",
    "demo_video_url",
    "logo",
    "screenshot",
})


class EnrichmentError(Exception):
    """Raised when enrichment fails."""
    pass


class DuplicateAgentError(Exception):
    """Raised when trying to create an agent that already exists."""
    
    def __init__(self, message: str, existing_agent: "Agent | None" = None):
        super().__init__(message)
        self.existing_agent = existing_agent


def is_valid_video_url(url: str | None) -> bool:
    """
    Check if URL is a valid video URL from supported platforms.
    
    Only YouTube, Vimeo, and Loom are supported.
    Returns False for images, screenshots, or other non-video URLs.
    """
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Check for supported video platforms
    video_domains = [
        "youtube.com",
        "youtu.be",
        "vimeo.com",
        "loom.com",
    ]
    
    # Reject common image extensions
    image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"]
    if any(url_lower.endswith(ext) for ext in image_extensions):
        return False
    
    # Check if URL contains a supported video domain
    return any(domain in url_lower for domain in video_domains)


class EnrichmentService:
    """
    Main entry point for agent enrichment.
    
    This service handles:
    - Scraping websites using Firecrawl
    - Enriching AgentSubmissions (stores URLs only)
    - Enriching existing Agents (downloads media immediately)
    - Creating Agents from enriched submissions

    TODO: User a back-up method/service for logos(ex logo.dev)
    """
    
    # Prompt to guide JSON extraction (used alongside schema)
    EXTRACTION_PROMPT = (
        "Extract accurate and factual information about this AI agent product. "
        "Focus on verifiable information from the page content. "
        "For pricing_model: UNKNOWN (if unclear), FREE (completely free), "
        "FREEMIUM (free with paid upgrades), PAID (requires payment), "
        "ENTERPRISE (custom pricing for businesses), CONTACT (pricing by request only). "
        "For category, choose the MOST appropriate: Commerce, Developer Tools, "
        "Digital Workers, General Assistant, Hardware + Software, Open Source, "
        "Research Labs, Task Automation, Voice Agents, Agent Platform, Blockchain, "
        "Business Automation, Customer Support, Marketing, AI Agent Framework, "
        "Social Media, AI Agency, Risk Management. "
        "For industry: UNKNOWN, GENERAL, HEALTHCARE, FINANCE, EDUCATION, ECOMMERCE, "
        "MARKETING, LEGAL, HR, TECH, CUSTOMER_SERVICE, RESEARCH, CONTENT. "
        "For demo_video_url: ONLY include actual video URLs from YouTube, Vimeo, or Loom. "
        "Do NOT include image URLs, screenshots, or non-video links. Leave null if no video found."
    )
    
    def __init__(self) -> None:
        """Initialize the enrichment service."""
        self.client = Firecrawl(api_key=settings.FIRECRAWL_API_KEY)
    
    # ─────────────────────────────────────────────────────────────
    # Core: Pure scraping (no persistence)
    # ─────────────────────────────────────────────────────────────
    
    def enrich(self, url: str) -> EnrichmentResult:
        """
        Scrape URL and return enrichment data.
        
        Extracts all data in a single API call:
        - JSON (structured data via schema)
        - Branding (logo, colors, fonts)
        - Markdown (raw content)
        - Screenshot (viewport capture)
        
        Args:
            url: Website URL to scrape
            
        Returns:
            EnrichmentResult with all extracted data
        """
        logger.info(f"Starting enrichment scrape for: {url}")
        
        try:
            # Single Firecrawl call with all formats
            response = self.client.scrape(
                url,
                formats=[
                    "markdown",
                    "screenshot",
                    "branding",
                    {
                        "type": "json",
                        "schema": AgentEnrichmentSchema.model_json_schema(),
                        "prompt": self.EXTRACTION_PROMPT,
                    },
                ],
            )
            
            # Handle response - SDK returns Pydantic model, not dict
            if response is None:
                return EnrichmentResult.from_error("No response from Firecrawl")
            
            # Helper to convert Pydantic models to dicts
            def to_dict_safe(obj):
                if obj is None:
                    return None
                if isinstance(obj, dict):
                    return obj
                if hasattr(obj, "model_dump"):
                    return obj.model_dump()
                if hasattr(obj, "dict"):
                    return obj.dict()
                return obj
            
            # Extract branding and logo URL (use getattr for Pydantic model)
            branding_raw = getattr(response, "branding", None)
            branding = to_dict_safe(branding_raw)
            
            # Get best logo URL (preferring non-SVG formats for ImageField compatibility)
            logo_url = self._extract_best_logo_url(branding)
            
            # Extract JSON content (also might be Pydantic model)
            json_data = to_dict_safe(getattr(response, "json", None))
            
            # Extract metadata (Firecrawl provides og_url which is often canonical)
            metadata = getattr(response, "metadata", None)
            og_url = None
            final_url = None
            if metadata:
                og_url = getattr(metadata, "og_url", None)
                final_url = getattr(metadata, "url", None)
            
            # Build result from response
            result = EnrichmentResult(
                success=True,
                content_data=json_data,
                branding_data=branding,
                logo_url=logo_url,
                markdown=getattr(response, "markdown", None),
                screenshot_url=getattr(response, "screenshot", None),
                og_url=og_url,
                final_url=final_url,
            )
            
            logger.info(f"Successfully scraped: {url}")
            return result
            
        except Exception as e:
            error_msg = f"Firecrawl scrape failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return EnrichmentResult.from_error(error_msg)
    
    # ─────────────────────────────────────────────────────────────
    # Flow A: AgentSubmission enrichment
    # ─────────────────────────────────────────────────────────────
    
    def enrich_submission(self, submission: AgentSubmission) -> AgentSubmission:
        """
        Enrich a submission by scraping its website.
        
        Features:
        - Aggregator URL extraction: If URL is from YC/ProductHunt/etc, 
          extract the real product URL and re-enrich
        - Name verification: Compare extracted name with submitted name
        - Canonical URL extraction: Parse canonical link from page
        
        Stores result in submission.enrichment_data (URLs only, no downloads).
        This allows review of the enriched data before creating an Agent.
        
        Args:
            submission: AgentSubmission to enrich
            
        Returns:
            Updated AgentSubmission with enrichment_data populated
        """
        logger.info(f"Enriching submission: {submission.agent_name}")
        
        original_url = submission.agent_website
        url_to_enrich = original_url
        
        # Preserve any sourcing metadata
        sourcing_metadata = {}
        if submission.enrichment_data and isinstance(submission.enrichment_data, dict):
            sourcing_metadata = submission.enrichment_data.get("_sourcing_metadata", {})
        
        # Check if this is an aggregator URL that needs URL extraction
        if is_aggregator_url(original_url) or sourcing_metadata.get("is_aggregator"):
            logger.info(f"Aggregator URL detected, extracting real product URL: {original_url}")
            
            extracted_url = self._extract_product_url_from_aggregator(original_url)
            
            if extracted_url and extracted_url != original_url:
                logger.info(f"Extracted real URL: {extracted_url}")
                url_to_enrich = extracted_url
                
                # Update submission with real URL
                submission.agent_website = extracted_url
                submission.save(update_fields=["agent_website"])
        
        # Enrich the (possibly updated) URL
        result = self.enrich(url_to_enrich)
        
        # Build enrichment data
        enrichment_dict = result.to_dict()
        
        # Add metadata about URL handling
        if original_url != url_to_enrich:
            enrichment_dict["_url_extraction"] = {
                "original_url": original_url,
                "extracted_url": url_to_enrich,
                "extraction_performed": True,
            }
        
        # Preserve sourcing metadata
        if sourcing_metadata:
            enrichment_dict["_sourcing_metadata"] = sourcing_metadata
        
        # Name verification
        if result.success and result.content_data:
            name_info = self._verify_agent_name(
                submitted_name=submission.agent_name,
                content_data=result.content_data,
            )
            enrichment_dict["_name_verification"] = name_info
            
            # Optionally update name if mismatch with high confidence
            if name_info.get("should_update") and name_info.get("extracted_name"):
                old_name = submission.agent_name
                submission.agent_name = name_info["extracted_name"][:200]
                logger.info(f"Updated agent name: '{old_name}' -> '{submission.agent_name}'")
        
        # Canonical URL extraction - prefer og_url from metadata, fallback to parsing
        canonical = result.og_url  # Firecrawl provides this from metadata
        if not canonical and result.markdown:
            canonical = self._extract_canonical_url(result.markdown)
        if canonical:
            enrichment_dict["_canonical_url"] = canonical
        
        submission.enrichment_data = enrichment_dict
        
        # Download images immediately (Firecrawl URLs expire in 24h!)
        # This ensures we have the images even if approval takes days
        fields_to_update = ["enrichment_data", "agent_name", "agent_website"]
        
        if result.success:
            # Download logo
            if result.logo_url:
                if self._download_submission_logo(submission, result.logo_url):
                    fields_to_update.append("logo")
                    enrichment_dict["_logo_downloaded"] = True
                else:
                    enrichment_dict["_logo_download_failed"] = True
            
            # Download screenshot
            if result.screenshot_url:
                if self._download_submission_screenshot(submission, result.screenshot_url):
                    fields_to_update.append("screenshot")
                    enrichment_dict["_screenshot_downloaded"] = True
                else:
                    enrichment_dict["_screenshot_download_failed"] = True
            
            # Update enrichment_data with download status
            submission.enrichment_data = enrichment_dict
        
        submission.save(update_fields=fields_to_update)
        
        logger.info(
            f"Submission enrichment {'succeeded' if result.success else 'failed'}: "
            f"{submission.agent_name}"
        )
        
        return submission
    
    def _extract_product_url_from_aggregator(self, aggregator_url: str) -> str | None:
        """
        Extract the real product URL from an aggregator page.
        
        Scrapes the aggregator page (YC, ProductHunt, etc.) and uses
        LLM extraction to find the actual product website.
        
        Args:
            aggregator_url: URL of the aggregator page
            
        Returns:
            Extracted product URL, or None if not found
        """
        try:
            logger.info(f"Extracting product URL from aggregator: {aggregator_url}")
            
            response = self.client.scrape(
                aggregator_url,
                formats=[
                    {
                        "type": "json",
                        "schema": get_aggregator_extraction_schema(),
                        "prompt": AGGREGATOR_URL_EXTRACTION_PROMPT,
                    }
                ],
            )
            
            if response is None:
                return None
            
            # Extract JSON data
            json_data = getattr(response, "json", None)
            if json_data is None:
                return None
            
            # Handle Pydantic model
            if hasattr(json_data, "model_dump"):
                json_data = json_data.model_dump()
            elif hasattr(json_data, "dict"):
                json_data = json_data.dict()
            
            product_url = json_data.get("product_website")
            confidence = json_data.get("confidence", 0)
            
            # Only use if confidence is reasonable
            if product_url and confidence >= 0.5:
                # Basic validation
                if product_url.startswith(("http://", "https://")):
                    return product_url
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract URL from aggregator: {e}")
            return None
    
    def _verify_agent_name(
        self,
        submitted_name: str,
        content_data: dict,
    ) -> dict:
        """
        Verify and optionally correct the agent name.
        
        Compares the submitted name with names extracted from the page.
        
        Args:
            submitted_name: Name as submitted/discovered
            content_data: Extracted content data from enrichment
            
        Returns:
            Dict with verification info:
            - matches: bool
            - extracted_name: str | None
            - confidence: float
            - should_update: bool
        """
        extracted_name = content_data.get("short_description", "")
        
        # Try to extract a name from short_description if it looks like a name
        # Usually the name is at the beginning or is the product name
        # For now, we'll look at the first few words
        
        # Simple heuristic: if short_description starts with a capitalized word
        # that's different from submitted name, it might be the actual name
        
        submitted_lower = submitted_name.lower().strip()
        
        # The content_data doesn't have a direct "name" field, so we compare
        # based on description patterns
        short_desc = content_data.get("short_description", "")
        
        result = {
            "submitted_name": submitted_name,
            "matches": True,  # Assume match by default
            "extracted_name": None,
            "confidence": 0.0,
            "should_update": False,
        }
        
        # If short_description is very different from name, flag it
        if short_desc:
            # Check if the submitted name appears in the description
            if submitted_lower not in short_desc.lower():
                result["matches"] = False
                result["confidence"] = 0.5  # Medium confidence
                # Don't auto-update name, just flag it
                result["should_update"] = False
        
        return result
    
    def _extract_canonical_url(self, markdown: str) -> str | None:
        """
        Extract canonical URL from page content.
        
        Looks for canonical link patterns in the markdown.
        
        Args:
            markdown: Page content as markdown
            
        Returns:
            Canonical URL if found, None otherwise
        """
        if not markdown:
            return None
        
        # Look for canonical URL patterns
        # Pattern 1: HTML link tag (might be in markdown)
        patterns = [
            r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
            r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']',
            r'canonical["\s:]+["\']?(https?://[^\s"\'<>]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                url = match.group(1)
                if url.startswith(("http://", "https://")):
                    return url
        
        return None
    
    def create_agent_from_submission(
        self,
        submission: AgentSubmission,
        user: Any | None = None,
    ) -> Agent:
        """
        Create an Agent from an enriched submission.
        
        Downloads media (logo, screenshot) and creates the Agent with
        all enriched data applied.
        
        Args:
            submission: Approved AgentSubmission with enrichment_data
            user: User approving the submission
            
        Returns:
            Created Agent with all enriched data applied
            
        Raises:
            EnrichmentError: If submission has no enrichment_data or enrichment failed
        """
        if not submission.enrichment_data:
            raise EnrichmentError(
                f"Submission '{submission.agent_name}' has no enrichment data. "
                "Call enrich_submission() first."
            )
        
        # Check if enrichment was successful
        if not submission.enrichment_data.get("success"):
            error_msg = submission.enrichment_data.get("error_message", "Unknown error")
            raise EnrichmentError(
                f"Submission '{submission.agent_name}' enrichment failed: {error_msg}. "
                "Re-run enrichment before approving."
            )
        
        logger.info(f"Creating agent from submission: {submission.agent_name}")
        
        # Check for duplicates before creating
        self._check_for_duplicate_agent(submission)
        
        data = submission.enrichment_data
        content = data.get("content_data") or {}
        
        with transaction.atomic():
            # Create base agent
            agent = Agent.objects.create(
                name=submission.agent_name,
                website=submission.agent_website,
                short_description=content.get("short_description", submission.agent_description)[:250],
                description=content.get("description", submission.agent_description),
                pricing_model=content.get("pricing_model", "UNKNOWN"),
                industry=content.get("industry", "UNKNOWN"),
                is_open_source=content.get("is_open_source"),
                twitter_url=content.get("twitter_url"),
                linkedin_url=content.get("linkedin_url"),
                demo_video_url=content.get("demo_video_url") if is_valid_video_url(content.get("demo_video_url")) else None,
                order=10,  # Default order to allow room for prioritization
            )
            
            # Handle category
            category_name = content.get("category")
            if category_name:
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={"slug": ""}
                )
                agent.categories.add(category)
            
            # Handle features
            features = content.get("features") or []
            Feature.objects.bulk_create([
                Feature(agent=agent, name=f) for f in features
            ])
            
            # Handle use cases
            use_cases = content.get("use_cases") or []
            UseCase.objects.bulk_create([
                UseCase(agent=agent, name=uc) for uc in use_cases
            ])
            
            # Copy logo from submission (preferred) or fallback to URL download
            # Images are downloaded during enrichment to avoid Firecrawl URL expiration
            if submission.logo:
                self._copy_submission_logo_to_agent(submission, agent)
            elif data.get("logo_url"):
                # Fallback: try URL (may fail if expired)
                logger.warning(f"No logo on submission, trying URL (may be expired)")
                self._download_logo(agent, data["logo_url"])
            
            # Copy screenshot from submission (preferred) or fallback to URL download
            if submission.screenshot:
                self._copy_submission_screenshot_to_agent(submission, agent)
            elif data.get("screenshot_url"):
                # Fallback: try URL (may fail if expired)
                logger.warning(f"No screenshot on submission, trying URL (may be expired)")
                self._download_screenshot(agent, data["screenshot_url"])
        
        logger.info(f"Created agent: {agent.name} (id={agent.pk})")
        return agent
    
    def _check_for_duplicate_agent(self, submission: AgentSubmission) -> None:
        """
        Check if submission would create a duplicate agent.
        
        Raises:
            DuplicateAgentError: If an agent with same website, name, or slug exists
        """
        from django.utils.text import slugify
        
        # Check for existing agent with same website
        existing = Agent.objects.filter(website=submission.agent_website).first()
        if existing:
            raise DuplicateAgentError(
                f"Agent with website '{submission.agent_website}' already exists: "
                f"'{existing.name}' (id={existing.pk})",
                existing_agent=existing,
            )
        
        # Check for existing agent with same name (case-insensitive)
        existing = Agent.objects.filter(name__iexact=submission.agent_name).first()
        if existing:
            raise DuplicateAgentError(
                f"Agent with name '{submission.agent_name}' already exists: "
                f"'{existing.name}' (id={existing.pk})",
                existing_agent=existing,
            )
        
        # Check for existing agent with same slug (e.g., "ZenFlow" and "Zenflow" → same slug)
        slug = slugify(submission.agent_name)
        existing = Agent.objects.filter(slug=slug).first()
        if existing:
            raise DuplicateAgentError(
                f"Agent with slug '{slug}' already exists: "
                f"'{existing.name}' (id={existing.pk})",
                existing_agent=existing,
            )
    
    def _copy_submission_logo_to_agent(self, submission: AgentSubmission, agent: Agent) -> bool:
        """
        Copy logo from submission to agent.
        
        Args:
            submission: AgentSubmission with logo
            agent: Agent to copy logo to
            
        Returns:
            True if copy succeeded, False otherwise
        """
        try:
            if not submission.logo:
                return False
            
            # Read the file content and save to agent
            submission.logo.seek(0)
            content = submission.logo.read()
            
            # Determine extension from submission logo name
            ext = Path(submission.logo.name).suffix or ".png"
            filename = f"{agent.slug}_logo{ext}"
            
            agent.logo.save(filename, ContentFile(content), save=True)
            logger.info(f"Copied logo from submission {submission.pk} to agent {agent.pk}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to copy logo from submission: {e}")
            return False
    
    def _copy_submission_screenshot_to_agent(self, submission: AgentSubmission, agent: Agent) -> bool:
        """
        Copy screenshot from submission to agent as a Screenshot record.
        
        Args:
            submission: AgentSubmission with screenshot
            agent: Agent to copy screenshot to
            
        Returns:
            True if copy succeeded, False otherwise
        """
        try:
            if not submission.screenshot:
                return False
            
            # Read the file content
            submission.screenshot.seek(0)
            content = submission.screenshot.read()
            
            # Determine extension from submission screenshot name
            ext = Path(submission.screenshot.name).suffix or ".png"
            filename = f"{agent.slug}_screenshot{ext}"
            
            # Create Screenshot record
            screenshot = Screenshot(
                agent=agent,
                is_primary=not agent.screenshots.exists(),
            )
            screenshot.image.save(filename, ContentFile(content), save=True)
            
            logger.info(f"Copied screenshot from submission {submission.pk} to agent {agent.pk}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to copy screenshot from submission: {e}")
            return False
    
    # ─────────────────────────────────────────────────────────────
    # Flow B: Existing Agent enrichment
    # ─────────────────────────────────────────────────────────────
    
    def enrich_agent(
        self,
        agent: Agent,
        fields: list[str] | None = None,
        user: Any | None = None,
    ) -> EnrichmentLog:
        """
        Enrich an existing agent and apply changes.
        
        Downloads media immediately and creates an audit log.
        
        Args:
            agent: Agent to enrich
            fields: Optional list of fields to update (None = all enrichable)
            user: User triggering the enrichment (for audit)
            
        Returns:
            EnrichmentLog with results
        """
        logger.info(f"Enriching agent: {agent.name} (fields={fields})")
        
        # Validate fields
        if fields:
            invalid = set(fields) - ENRICHABLE_FIELDS
            if invalid:
                raise EnrichmentError(f"Invalid fields: {invalid}")
            fields_to_update = set(fields)
        else:
            fields_to_update = ENRICHABLE_FIELDS
        
        # Capture previous state
        previous_data = self._capture_agent_state(agent)
        
        # Scrape the website
        result = self.enrich(agent.website)
        
        # If scraping failed, create error log
        if not result.success:
            return EnrichmentLog.objects.create(
                agent=agent,
                previous_data=previous_data,
                extracted_data=result.to_dict(),
                applied_fields=[],
                success=False,
                error_message=result.error_message,
                created_by=user,
            )
        
        # Apply changes
        with transaction.atomic():
            applied_fields = self._apply_fields_to_agent(
                agent, result, fields_to_update
            )
            
            # Create success log
            log = EnrichmentLog.objects.create(
                agent=agent,
                previous_data=previous_data,
                extracted_data=result.to_dict(),
                applied_fields=applied_fields,
                success=True,
                created_by=user,
            )
        
        logger.info(
            f"Agent enrichment complete: {agent.name} "
            f"(applied: {applied_fields})"
        )
        return log
    
    def enrich_agents(
        self,
        agents: list[Agent],
        fields: list[str] | None = None,
        user: Any | None = None,
    ) -> list[EnrichmentLog]:
        """
        Enrich multiple existing agents.
        
        Args:
            agents: List of agents to enrich
            fields: Optional list of fields to update
            user: User triggering the enrichment
            
        Returns:
            List of EnrichmentLog entries
        """
        logs = []
        for agent in agents:
            try:
                log = self.enrich_agent(agent, fields=fields, user=user)
                logs.append(log)
            except Exception as e:
                logger.error(f"Failed to enrich {agent.name}: {e}", exc_info=True)
                # Create error log
                logs.append(EnrichmentLog.objects.create(
                    agent=agent,
                    previous_data=self._capture_agent_state(agent),
                    extracted_data={},
                    applied_fields=[],
                    success=False,
                    error_message=str(e),
                    created_by=user,
                ))
        return logs
    
    # ─────────────────────────────────────────────────────────────
    # Helpers (internal)
    # ─────────────────────────────────────────────────────────────
    
    def _capture_agent_state(self, agent: Agent) -> dict:
        """Capture current agent state for change tracking."""
        return {
            "short_description": agent.short_description,
            "description": agent.description,
            "features": list(agent.feature_set.values_list("name", flat=True)),
            "use_cases": list(agent.use_case_set.values_list("name", flat=True)),
            "pricing_model": agent.pricing_model,
            "categories": list(agent.categories.values_list("name", flat=True)),
            "is_open_source": agent.is_open_source,
            "industry": agent.industry,
            "twitter_url": agent.twitter_url,
            "linkedin_url": agent.linkedin_url,
            "demo_video_url": agent.demo_video_url,
            "logo": agent.logo.name if agent.logo else None,
            "screenshots": list(agent.screenshots.values_list("image", flat=True)),
        }
    
    def _apply_fields_to_agent(
        self,
        agent: Agent,
        result: EnrichmentResult,
        fields: set[str],
    ) -> list[str]:
        """
        Apply enrichment data to agent.
        
        Args:
            agent: Agent to update
            result: Enrichment result with data
            fields: Set of field names to update
            
        Returns:
            List of field names that were actually updated
        """
        applied = []
        content = result.content_data or {}
        
        # Simple text/choice fields
        # Transforms return None for empty values to preserve existing agent data
        simple_fields = {
            "short_description": lambda v: v[:250] if v else None,
            "description": lambda v: v if v else None,
            "pricing_model": lambda v: v if v else None,
            "industry": lambda v: v if v else None,
            "is_open_source": lambda v: v,
            "twitter_url": lambda v: v if v else None,
            "linkedin_url": lambda v: v if v else None,
            "demo_video_url": lambda v: v if is_valid_video_url(v) else None,
        }
        
        for field_name, transform in simple_fields.items():
            if field_name in fields and field_name in content:
                value = transform(content[field_name])
                if value is not None:
                    setattr(agent, field_name, value)
                    applied.append(field_name)
        
        agent.save()
        
        # Features (related model)
        if "features" in fields and content.get("features"):
            agent.feature_set.all().delete()
            Feature.objects.bulk_create([
                Feature(agent=agent, name=f) for f in content["features"]
            ])
            applied.append("features")
        
        # Use cases (related model)
        if "use_cases" in fields and content.get("use_cases"):
            agent.use_case_set.all().delete()
            UseCase.objects.bulk_create([
                UseCase(agent=agent, name=uc) for uc in content["use_cases"]
            ])
            applied.append("use_cases")
        
        # Category (M2M)
        if "category" in fields and content.get("category"):
            category, _ = Category.objects.get_or_create(
                name=content["category"],
                defaults={"slug": ""}
            )
            agent.categories.clear()
            agent.categories.add(category)
            applied.append("category")
        
        # Logo (download)
        if "logo" in fields and result.logo_url:
            if self._download_logo(agent, result.logo_url):
                applied.append("logo")
        
        # Screenshot (download)
        if "screenshot" in fields and result.screenshot_url:
            if self._download_screenshot(agent, result.screenshot_url):
                applied.append("screenshot")
        
        return applied
    
    def _download_logo(self, agent: Agent, logo_url: str) -> bool:
        """
        Download logo from URL and save to agent.logo field.
        
        Skips SVG files as Django's ImageField doesn't support them.
        
        Args:
            agent: Agent to update
            logo_url: URL of the logo image
            
        Returns:
            True if download succeeded, False otherwise
        """
        # Skip SVG files (not compatible with Django ImageField/Pillow)
        if self._is_svg_url(logo_url):
            logger.warning(f"Skipping SVG logo for {agent.name}: {logo_url}")
            return False
        
        try:
            logger.info(f"Downloading logo for {agent.name}: {logo_url}")
            
            response = httpx.get(logo_url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Determine file extension from URL or content-type
            content_type = response.headers.get("content-type", "")
            
            # Skip SVG by content-type (in case URL didn't indicate it)
            if "svg" in content_type.lower():
                logger.warning(f"Skipping SVG logo (by content-type) for {agent.name}")
                return False
            
            ext = self._get_image_extension(logo_url, content_type)
            
            # Save to agent
            filename = f"{agent.slug}_logo{ext}"
            agent.logo.save(filename, ContentFile(response.content), save=True)
            
            logger.info(f"Logo saved for {agent.name}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to download logo for {agent.name}: {e}")
            return False
    
    def _download_screenshot(self, agent: Agent, screenshot_url: str) -> bool:
        """
        Download screenshot from URL and create Screenshot record.
        
        Args:
            agent: Agent to attach screenshot to
            screenshot_url: URL of the screenshot image
            
        Returns:
            True if download succeeded, False otherwise
        """
        try:
            logger.info(f"Downloading screenshot for {agent.name}: {screenshot_url}")
            
            response = httpx.get(screenshot_url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get("content-type", "")
            ext = self._get_image_extension(screenshot_url, content_type)
            
            # Create screenshot record
            screenshot = Screenshot(
                agent=agent,
                is_primary=not agent.screenshots.exists(),
            )
            
            filename = f"{agent.slug}_screenshot{ext}"
            screenshot.image.save(filename, ContentFile(response.content), save=True)
            
            logger.info(f"Screenshot saved for {agent.name}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to download screenshot for {agent.name}: {e}")
            return False
    
    def _get_image_extension(self, url: str, content_type: str) -> str:
        """Determine image file extension from URL or content-type."""
        # Try content-type first
        type_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }
        
        for mime, ext in type_map.items():
            if mime in content_type:
                return ext
        
        # Try URL extension
        path = urlparse(url).path.lower()
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
            if path.endswith(ext):
                return ext if ext != ".jpeg" else ".jpg"
        
        # Default to PNG
        return ".png"
    
    def _is_svg_url(self, url: str) -> bool:
        """Check if URL points to an SVG file (not compatible with Django ImageField)."""
        if not url:
            return False
        path = urlparse(url).path.lower()
        return path.endswith(".svg")
    
    def _extract_best_logo_url(self, branding: dict | None) -> str | None:
        """
        Extract the best logo URL from Firecrawl branding data.
        
        Prefers non-SVG formats since Django's ImageField doesn't support SVG.
        Falls back to ogImage if logo is SVG.
        
        Priority order:
        1. branding.logo (if not SVG)
        2. branding.images.logo (if not SVG)
        3. branding.images.ogImage (usually PNG/JPG, good quality)
        4. branding.logo or branding.images.logo (even if SVG, as last resort)
        
        Args:
            branding: Firecrawl branding dict
            
        Returns:
            Best logo URL or None
        """
        if not branding:
            return None
        
        images = branding.get("images") or {}
        
        # Collect all potential logo URLs
        logo_primary = branding.get("logo")
        logo_images = images.get("logo")
        og_image = images.get("ogImage")
        
        # Try non-SVG options first
        for url in [logo_primary, logo_images]:
            if url and not self._is_svg_url(url):
                return url
        
        # ogImage is usually PNG/JPG and good quality
        if og_image and not self._is_svg_url(og_image):
            logger.info(f"Using ogImage as logo fallback (primary logo is SVG)")
            return og_image
        
        # Last resort: return SVG if that's all we have
        # Download will likely fail but at least we tried
        if logo_primary:
            logger.warning(f"Only SVG logo available: {logo_primary}")
            return logo_primary
        if logo_images:
            logger.warning(f"Only SVG logo available: {logo_images}")
            return logo_images
        
        return None
    
    # ─────────────────────────────────────────────────────────────
    # Submission Media Download (Firecrawl URLs expire in 24h!)
    # ─────────────────────────────────────────────────────────────
    
    def _download_submission_logo(self, submission: AgentSubmission, logo_url: str) -> bool:
        """
        Download logo from URL and save to submission.logo field.
        
        Called immediately during enrichment to avoid URL expiration.
        Skips SVG files as Django's ImageField doesn't support them.
        
        Args:
            submission: AgentSubmission to update
            logo_url: URL of the logo image
            
        Returns:
            True if download succeeded, False otherwise
        """
        # Skip SVG files (not compatible with Django ImageField/Pillow)
        if self._is_svg_url(logo_url):
            logger.warning(f"Skipping SVG logo for submission {submission.pk}: {logo_url}")
            return False
        
        try:
            logger.info(f"Downloading logo for submission {submission.pk}: {logo_url}")
            
            response = httpx.get(logo_url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Determine file extension from URL or content-type
            content_type = response.headers.get("content-type", "")
            
            # Skip SVG by content-type (in case URL didn't indicate it)
            if "svg" in content_type.lower():
                logger.warning(f"Skipping SVG logo (by content-type) for submission {submission.pk}")
                return False
            
            ext = self._get_image_extension(logo_url, content_type)
            
            # Save to submission
            filename = f"submission_{submission.pk}_logo{ext}"
            submission.logo.save(filename, ContentFile(response.content), save=False)
            
            logger.info(f"Logo saved for submission {submission.pk}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to download logo for submission {submission.pk}: {e}")
            return False
    
    def _download_submission_screenshot(self, submission: AgentSubmission, screenshot_url: str) -> bool:
        """
        Download screenshot from URL and save to submission.screenshot field.
        
        Called immediately during enrichment to avoid URL expiration.
        
        Args:
            submission: AgentSubmission to update
            screenshot_url: URL of the screenshot image
            
        Returns:
            True if download succeeded, False otherwise
        """
        try:
            logger.info(f"Downloading screenshot for submission {submission.pk}: {screenshot_url}")
            
            response = httpx.get(screenshot_url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get("content-type", "")
            ext = self._get_image_extension(screenshot_url, content_type)
            
            # Save to submission
            filename = f"submission_{submission.pk}_screenshot{ext}"
            submission.screenshot.save(filename, ContentFile(response.content), save=False)
            
            logger.info(f"Screenshot saved for submission {submission.pk}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to download screenshot for submission {submission.pk}: {e}")
            return False

