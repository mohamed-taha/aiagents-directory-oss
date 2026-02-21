"""
Pydantic schemas for agent pipeline.

These schemas define the structure for:
- Firecrawl JSON extraction (enrichment)
- Enrichment results
- AI review results
"""

from dataclasses import dataclass, asdict
from typing import Literal

from pydantic import BaseModel, Field


# Valid values for constrained fields
PricingModelType = Literal["UNKNOWN", "FREE", "FREEMIUM", "PAID", "ENTERPRISE", "CONTACT"]
IndustryType = Literal[
    "UNKNOWN", "GENERAL", "HEALTHCARE", "FINANCE", "EDUCATION",
    "ECOMMERCE", "MARKETING", "LEGAL", "HR", "TECH",
    "CUSTOMER_SERVICE", "RESEARCH", "CONTENT"
]


class AgentEnrichmentSchema(BaseModel):
    """
    Schema for Firecrawl JSON extraction.
    
    This schema defines what structured data we want to extract
    from an agent's website using Firecrawl's JSON mode.
    """
    
    short_description: str | None = Field(
        None,
        description="A brief one-line description of the AI agent (max 250 chars)"
    )
    
    description: str | None = Field(
        None,
        description="Full detailed description of the AI agent and its capabilities"
    )
    
    features: list[str] | None = Field(
        None,
        description="List of key features and capabilities of the agent"
    )
    
    use_cases: list[str] | None = Field(
        None,
        description="List of primary use cases the agent is designed for"
    )
    
    pricing_model: PricingModelType | None = Field(
        None,
        description=(
            "Pricing model for the agent. Must be one of: "
            "UNKNOWN, FREE, FREEMIUM, PAID, ENTERPRISE, CONTACT"
        )
    )
    
    category: str | None = Field(
        None,
        description=(
            "Primary category of the agent. Should be ONE of: "
            "Commerce, Developer Tools, Digital Workers, General Assistant, "
            "Hardware + Software, Open Source, Research Labs, Task Automation, "
            "Voice Agents, Agent Platform, Blockchain, Business Automation, "
            "Customer Support, Marketing, AI Agent Framework, Social Media, "
            "AI Agency, Risk Management"
        )
    )
    
    is_open_source: bool | None = Field(
        None,
        description="Whether the agent's source code is publicly available"
    )
    
    industry: IndustryType | None = Field(
        None,
        description=(
            "Primary industry or sector the agent serves. Must be one of: "
            "UNKNOWN, GENERAL, HEALTHCARE, FINANCE, EDUCATION, ECOMMERCE, "
            "MARKETING, LEGAL, HR, TECH, CUSTOMER_SERVICE, RESEARCH, CONTENT"
        )
    )
    
    twitter_url: str | None = Field(
        None,
        description="URL of the agent's or company's Twitter/X profile"
    )
    
    linkedin_url: str | None = Field(
        None,
        description="URL of the agent's or company's LinkedIn profile"
    )
    
    demo_video_url: str | None = Field(
        None,
        description="URL of a demo video (YouTube, Vimeo, or Loom)"
    )


@dataclass
class EnrichmentResult:
    """
    Internal representation of scraped enrichment data.
    
    This dataclass holds all data extracted from a Firecrawl scrape
    operation across all formats (json, branding, markdown, screenshot).
    """
    
    success: bool
    error_message: str | None = None
    
    # From JSON format (structured extraction)
    content_data: dict | None = None
    
    # From branding format
    branding_data: dict | None = None
    logo_url: str | None = None
    
    # From markdown format (raw page content)
    markdown: str | None = None
    
    # From screenshot format
    screenshot_url: str | None = None
    
    # From metadata (Firecrawl provides these)
    og_url: str | None = None  # Often same as canonical URL
    final_url: str | None = None  # URL after redirects
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return asdict(self)
    
    @classmethod
    def from_error(cls, error_message: str) -> "EnrichmentResult":
        """Create a failed result with an error message."""
        return cls(success=False, error_message=error_message)
    
    @classmethod
    def from_firecrawl_response(cls, response: dict) -> "EnrichmentResult":
        """
        Create an EnrichmentResult from a Firecrawl scrape response.
        
        Args:
            response: Raw response from Firecrawl scrape API
            
        Returns:
            EnrichmentResult with parsed data
        """
        if not response.get("success"):
            return cls.from_error(
                response.get("error", "Unknown error from Firecrawl")
            )
        
        data = response.get("data", {})
        
        # Extract branding data and logo URL
        branding = data.get("branding")
        logo_url = None
        if branding and branding.get("images"):
            logo_url = branding["images"].get("logo")
        
        return cls(
            success=True,
            content_data=data.get("json"),
            branding_data=branding,
            logo_url=logo_url,
            markdown=data.get("markdown"),
            screenshot_url=data.get("screenshot"),
        )


# ─────────────────────────────────────────────────────────────
# Review Schemas
# ─────────────────────────────────────────────────────────────

ReviewDecision = Literal["approved", "rejected", "needs_review"]


class ReviewResult(BaseModel):
    """
    Output from AI review agent.
    
    Stored in AgentSubmission.ai_review_result as JSON.
    """
    
    decision: ReviewDecision = Field(
        description="The review decision: approved, rejected, or needs_review"
    )
    
    is_ai_agent: bool = Field(
        description="Whether the product is determined to be an AI agent or AI agency"
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0"
    )
    
    reasoning: str = Field(
        description="Explanation for the decision"
    )
    
    flags: list[str] = Field(
        default_factory=list,
        description="Flags indicating issues (e.g., 'not_ai_agent', 'prohibited_content')"
    )
    
    auto_applied: bool = Field(
        default=False,
        description="Whether the decision was automatically applied to submission status"
    )
