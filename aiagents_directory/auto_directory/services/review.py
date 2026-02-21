"""
AI-powered review service for agents and submissions.

This module provides the ReviewService class for reviewing agents
using a Pydantic AI agent to determine if they are valid AI agents.

All methods are synchronous (uses Pydantic AI's run_sync internally).

Usage:
    service = ReviewService()
    
    # Pure review
    result = service.review(name, website, enrichment_data, markdown)
    
    # Submission wrapper (persists result)
    submission = service.review_submission(submission)
    
    # Agent wrapper (no persistence)
    result = service.review_agent(agent)
"""

import logging
import os
from typing import Any, TYPE_CHECKING

from pydantic_ai import Agent as PydanticAgent

from aiagents_directory.agents.models import AgentSubmission, SubmissionStatus
from aiagents_directory.auto_directory.schemas import EnrichmentResult, ReviewResult

if TYPE_CHECKING:
    from aiagents_directory.agents.models import Agent


logger = logging.getLogger(__name__)

# Optional Logfire instrumentation (configure via LOGFIRE_TOKEN env var)
if os.environ.get("LOGFIRE_TOKEN"):
    try:
        import logfire
        logfire.configure()
        logfire.instrument_pydantic_ai()
        logfire.instrument_httpx(capture_all=True)
    except ImportError:
        pass


# ─────────────────────────────────────────────────────────────
# Pydantic AI Review Agent
# ─────────────────────────────────────────────────────────────

REVIEW_INSTRUCTIONS = """
You are a reviewer for AiAgents.Directory, a curated directory of AI agents.

Your task is to determine if the submitted product qualifies for inclusion.

## What qualifies as an AI Agent:
- Autonomous software that performs tasks using AI/ML
- Software agents that can take actions on behalf of users
- AI-powered automation tools with agent-like capabilities
- Companies/agencies that BUILD AI agents (AI agencies)
- Open source AI agent frameworks or libraries (from GitHub)

## What does NOT qualify:
- Regular SaaS tools without agent/autonomous capabilities
- Simple chatbots or basic API wrappers
- Static websites or landing pages
- Products unrelated to AI agents
- General AI tools that aren't agents (e.g., image generators without automation)

## IMPORTANT: Detect and REJECT these page types:

### Template/Workflow Pages (REJECT with flag "is_template_page"):
- n8n workflow templates or integrations
- Make.com (Integromat) scenarios or templates
- Zapier integrations or templates
- Relay.app playbooks
- Any page showing a user-built automation, not a product

### Feature Pages of Larger Products (REJECT with flag "is_feature_not_product"):
- A feature page within a larger company's website (e.g., "ProductX Agent" as a feature)
- Sub-products that aren't standalone offerings
- Plugin or extension pages for other platforms

### Directory/Aggregator Listings (REJECT with flag "is_aggregator_listing"):
- Pages from AI agent directories listing other products
- Product Hunt, YCombinator, Crunchbase company pages
- News articles or blog posts ABOUT an agent (not the agent itself)
- Review sites or comparison pages

### Blog Posts/Articles (REJECT with flag "is_article_not_landing"):
- Blog posts discussing AI agents
- News articles about AI agent releases
- Tutorial or documentation pages
- Help center or support pages

### Academic/Research (REJECT with flag "is_academic_paper"):
- arXiv papers or preprints
- Academic research pages
- Conference paper listings

## Prohibited content (must reject with flag "prohibited_content"):
- Adult/NSFW content
- Illegal services or products
- Scams, fraud, or deceptive products
- Malware or security threats

## Input you will receive:
1. AGENT NAME: The name of the product/company
2. WEBSITE: The URL of the product
3. ENRICHMENT DATA: Structured data extracted from the website (description, features, use cases, etc.)
4. RAW MARKDOWN (optional): The full page content if available for additional context

## Your output:
- decision: "approved" if it qualifies, "rejected" if not, "needs_review" if uncertain
- is_ai_agent: true if it's an AI agent or AI agency
- confidence: 0.0 to 1.0 (how confident you are in your decision)
- reasoning: Clear explanation of your decision
- flags: List any issues found (use the specific flags mentioned above)

## Decision guidelines:
- APPROVE: Clearly an AI agent product with its own landing page
- REJECT: Matches any of the "REJECT" patterns above, or is clearly not an AI agent
- NEEDS_REVIEW: Uncertain cases, edge cases, or when you can't determine from available data

Be thorough but fair. Use specific flags to explain rejection reasons.
"""

# Create the Pydantic AI agent
review_agent = PydanticAgent(
    "openai:gpt-5.1",
    output_type=ReviewResult,
    instructions=REVIEW_INSTRUCTIONS,
)


# ─────────────────────────────────────────────────────────────
# Review Service
# ─────────────────────────────────────────────────────────────

class ReviewService:
    """
    AI-powered review service for agents and submissions.
    
    Uses Pydantic AI to determine if products are valid AI agents.
    
    Methods:
        review(): Pure review - takes raw data, returns ReviewResult
        review_submission(): Wrapper for AgentSubmission - persists result
        review_agent(): Wrapper for Agent - returns result without persistence
    """
    
    # Confidence threshold for auto-applying decisions
    CONFIDENCE_THRESHOLD = 0.7
    
    def __init__(self, confidence_threshold: float | None = None) -> None:
        """
        Initialize the review service.
        
        Args:
            confidence_threshold: Override default confidence threshold
        """
        self.confidence_threshold = confidence_threshold or self.CONFIDENCE_THRESHOLD
    
    def review(
        self,
        name: str,
        website: str,
        enrichment_data: EnrichmentResult | dict | None = None,
        raw_markdown: str | None = None,
    ) -> ReviewResult:
        """
        Run AI review on agent data (sync).
        
        Args:
            name: Name of the agent/product
            website: Website URL
            enrichment_data: Structured enrichment data (EnrichmentResult or dict)
            raw_markdown: Optional raw page content for additional context
            
        Returns:
            ReviewResult with decision, confidence, and reasoning
        """
        logger.info(f"Starting AI review for: {name} ({website})")
        
        # Build the prompt with available data
        prompt = self._build_review_prompt(name, website, enrichment_data, raw_markdown)
        
        try:
            # Run the Pydantic AI agent (sync)
            result = review_agent.run_sync(prompt)
            
            logger.info(
                f"Review complete for {name}: "
                f"decision={result.output.decision}, "
                f"confidence={result.output.confidence:.2f}"
            )
            
            return result.output
            
        except Exception as e:
            logger.error(f"Review failed for {name}: {e}", exc_info=True)
            # Return a needs_review result on error
            return ReviewResult(
                decision="needs_review",
                is_ai_agent=False,
                confidence=0.0,
                reasoning=f"Review failed due to error: {str(e)}",
                flags=["review_error"],
            )
    
    def review_submission(
        self,
        submission: AgentSubmission,
        auto_apply: bool = False,
    ) -> AgentSubmission:
        """
        Review a submission and update its fields.
        
        Updates:
        - ai_review_result: ReviewResult as JSON
        - needs_manual_review: True if confidence < threshold
        - status: Only if auto_apply=True and confidence >= threshold
        
        Args:
            submission: AgentSubmission to review
            auto_apply: If True, automatically apply approved/rejected status
            
        Returns:
            Updated submission (saved to database)
        """
        logger.info(f"Reviewing submission: {submission.agent_name}")
        
        # Parse enrichment data if available
        enrichment_data = None
        raw_markdown = None
        
        if submission.enrichment_data:
            enrichment_data = submission.enrichment_data
            # Extract markdown if present
            raw_markdown = enrichment_data.get("markdown")
        
        # Run the review
        result = self.review(
            name=submission.agent_name,
            website=submission.agent_website,
            enrichment_data=enrichment_data,
            raw_markdown=raw_markdown,
        )
        
        # Determine if manual review is needed
        needs_manual = result.confidence < self.confidence_threshold
        
        # Determine if we should auto-apply the decision
        should_apply = (
            auto_apply
            and not needs_manual
            and result.decision in ("approved", "rejected")
        )
        
        # Update the result with auto_applied flag
        result.auto_applied = should_apply
        
        # Update submission fields
        submission.ai_review_result = result.model_dump()
        submission.needs_manual_review = needs_manual
        
        # Auto-apply status if conditions met
        if should_apply:
            if result.decision == "approved":
                submission.status = SubmissionStatus.APPROVED
                logger.info(f"Auto-approved submission: {submission.agent_name}")
            elif result.decision == "rejected":
                submission.status = SubmissionStatus.REJECTED
                logger.info(f"Auto-rejected submission: {submission.agent_name}")
        
        # Save the submission
        submission.save()
        
        logger.info(
            f"Review saved for {submission.agent_name}: "
            f"needs_manual_review={needs_manual}, auto_applied={should_apply}"
        )
        
        return submission
    
    def review_agent(self, agent: "Agent") -> ReviewResult:
        """
        Review an existing agent.
        
        Builds enrichment-like data from agent fields and runs review.
        Does NOT persist result (Agent model has no review fields).
        Caller decides what to do with the result.
        
        Args:
            agent: Agent instance to review
            
        Returns:
            ReviewResult with decision, confidence, and reasoning
        """
        logger.info(f"Reviewing agent: {agent.name} (id={agent.pk})")
        
        # Build enrichment-like data from agent fields
        enrichment_data = {
            "success": True,
            "content_data": {
                "short_description": agent.short_description,
                "description": agent.description,
                "features": list(agent.feature_set.values_list("name", flat=True)),
                "use_cases": list(agent.use_case_set.values_list("name", flat=True)),
                "category": agent.categories.first().name if agent.categories.exists() else None,
                "industry": agent.industry,
                "pricing_model": agent.pricing_model,
            },
        }
        
        # Run the review (no persistence)
        result = self.review(
            name=agent.name,
            website=agent.website,
            enrichment_data=enrichment_data,
            raw_markdown=None,  # Agent doesn't store markdown
        )
        
        logger.info(
            f"Agent review complete: {agent.name} - "
            f"decision={result.decision}, confidence={result.confidence:.2f}"
        )
        
        return result
    
    def _build_review_prompt(
        self,
        name: str,
        website: str,
        enrichment_data: EnrichmentResult | dict | None,
        raw_markdown: str | None,
    ) -> str:
        """Build the prompt for the review agent."""
        parts = [
            f"## AGENT NAME\n{name}",
            f"\n## WEBSITE\n{website}",
        ]
        
        # Add enrichment data
        if enrichment_data:
            # Handle both EnrichmentResult and dict
            if isinstance(enrichment_data, EnrichmentResult):
                data = enrichment_data.to_dict()
            else:
                data = enrichment_data
            
            content = data.get("content_data") or {}
            
            parts.append("\n## ENRICHMENT DATA (structured extraction from website)")
            
            if content.get("short_description"):
                parts.append(f"\n**Short Description:** {content['short_description']}")
            
            if content.get("description"):
                parts.append(f"\n**Full Description:** {content['description']}")
            
            if content.get("features"):
                features = "\n".join(f"- {f}" for f in content["features"])
                parts.append(f"\n**Features:**\n{features}")
            
            if content.get("use_cases"):
                use_cases = "\n".join(f"- {uc}" for uc in content["use_cases"])
                parts.append(f"\n**Use Cases:**\n{use_cases}")
            
            if content.get("category"):
                parts.append(f"\n**Category:** {content['category']}")
            
            if content.get("industry"):
                parts.append(f"\n**Industry:** {content['industry']}")
            
            if content.get("pricing_model"):
                parts.append(f"\n**Pricing:** {content['pricing_model']}")
        
        # Add raw markdown if available
        if raw_markdown:
            # Truncate if too long (keep first 4000 chars)
            truncated = raw_markdown[:4000]
            if len(raw_markdown) > 4000:
                truncated += "\n\n[... content truncated ...]"
            
            parts.append(f"\n## RAW MARKDOWN (full page content)\n{truncated}")
        
        return "\n".join(parts)

