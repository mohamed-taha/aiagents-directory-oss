"""
Agent sourcing service.

This module provides the SourcingService class for orchestrating
automated agent discovery from multiple sources.

Usage:
    service = SourcingService()
    
    # Run all enabled sources
    run = service.run_all(auto_enrich=True)
    
    # Run specific source
    run = service.run_source("serp", limit=50)
    
    # Run with custom source instance
    from aiagents_directory.auto_directory.sources import SerpSource
    source = SerpSource(queries=["AI coding agent"])
    run = service.run(source)
"""

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from aiagents_directory.agents.models import (
    Agent,
    AgentSubmission,
    SubmissionSource,
    SubmissionStatus,
)
from aiagents_directory.auto_directory.filters import (
    get_block_reason,
    get_url_classification,
)
from aiagents_directory.auto_directory.models import SourcingRun
from aiagents_directory.auto_directory.sources.base import (
    BaseSource,
    DiscoveredAgent,
    normalize_url,
)


if TYPE_CHECKING:
    from aiagents_directory.users.models import User


logger = logging.getLogger(__name__)


class SourcingService:
    """
    Orchestrates agent discovery from multiple sources.
    
    Responsibilities:
    - Run source plugins to discover agents
    - Deduplicate against existing agents and submissions
    - Create AgentSubmission entries for new discoveries
    - Track sourcing runs for audit/monitoring
    - Optionally trigger enrichment for new submissions
    
    Example:
        service = SourcingService()
        
        # Run all registered sources
        run = service.run_all()
        print(f"Discovered {run.discovered_count}, {run.new_count} new")
        
        # Run with auto-enrichment
        run = service.run_all(auto_enrich=True)
    """
    
    def __init__(self, sources: list[BaseSource] | None = None) -> None:
        """
        Initialize the sourcing service.
        
        Args:
            sources: Optional list of source instances to use.
                     If not provided, uses default sources.
        """
        self.sources = sources or self._get_default_sources()
    
    def _get_default_sources(self) -> list[BaseSource]:
        """Get default source instances."""
        from aiagents_directory.auto_directory.sources import SerpSource
        
        # Default: only SERP source
        # UrlSource requires explicit URLs so not included by default
        return [SerpSource()]
    
    def run_all(
        self,
        limit_per_source: int = 50,
        auto_enrich: bool = False,
        user: "User | None" = None,
    ) -> list[SourcingRun]:
        """
        Run all registered sources.
        
        Args:
            limit_per_source: Max agents to discover per source
            auto_enrich: Whether to trigger enrichment for new submissions
            user: User triggering the run (for audit)
            
        Returns:
            List of SourcingRun records (one per source)
        """
        runs = []
        
        for source in self.sources:
            if not source.is_available():
                logger.warning(f"Source '{source.source_id}' is not available, skipping")
                continue
            
            try:
                run = self.run(
                    source,
                    limit=limit_per_source,
                    auto_enrich=auto_enrich,
                    user=user,
                )
                runs.append(run)
            except Exception as e:
                logger.error(f"Failed to run source '{source.source_id}': {e}", exc_info=True)
                # Create error run record
                error_run = SourcingRun.objects.create(
                    source_id=source.source_id,
                    success=False,
                    error_message=str(e),
                    completed_at=timezone.now(),
                    created_by=user,
                )
                runs.append(error_run)
        
        return runs
    
    def run_source(
        self,
        source_id: str,
        limit: int = 100,
        auto_enrich: bool = False,
        user: "User | None" = None,
    ) -> SourcingRun:
        """
        Run a specific source by ID.
        
        Args:
            source_id: ID of the source to run (e.g., "serp", "url")
            limit: Max agents to discover
            auto_enrich: Whether to trigger enrichment
            user: User triggering the run
            
        Returns:
            SourcingRun record
            
        Raises:
            ValueError: If source_id not found in registered sources
        """
        source = next(
            (s for s in self.sources if s.source_id == source_id),
            None
        )
        
        if source is None:
            raise ValueError(f"Unknown source: {source_id}")
        
        return self.run(source, limit=limit, auto_enrich=auto_enrich, user=user)
    
    def run(
        self,
        source: BaseSource,
        limit: int = 100,
        auto_enrich: bool = False,
        user: "User | None" = None,
    ) -> SourcingRun:
        """
        Run a single source and create submissions for new discoveries.
        
        Args:
            source: Source instance to run
            limit: Max agents to discover
            auto_enrich: Whether to trigger enrichment for new submissions
            user: User triggering the run
            
        Returns:
            SourcingRun record with statistics
        """
        logger.info(f"Starting sourcing run: source={source.source_id}, limit={limit}")
        
        # Create run record
        run = SourcingRun.objects.create(
            source_id=source.source_id,
            config=source.get_config() if hasattr(source, "get_config") else {},
            created_by=user,
        )
        
        try:
            # Discover agents from source
            discovered = source.discover(limit=limit)
            run.discovered_count = len(discovered)
            
            # Deduplicate and create submissions
            created_submissions = self._process_discoveries(
                discovered,
                source_id=source.source_id,
            )
            
            run.new_count = len(created_submissions)
            run.skipped_count = run.discovered_count - run.new_count
            run.created_submission_ids = [s.pk for s in created_submissions]
            run.success = True
            run.completed_at = timezone.now()
            run.save()
            
            logger.info(
                f"Sourcing run complete: source={source.source_id}, "
                f"discovered={run.discovered_count}, new={run.new_count}, "
                f"skipped={run.skipped_count}"
            )
            
            # Optionally trigger enrichment
            if auto_enrich and created_submissions:
                self._enrich_submissions(created_submissions)
            
            return run
            
        except Exception as e:
            logger.error(f"Sourcing run failed: {e}", exc_info=True)
            run.success = False
            run.error_message = str(e)
            run.completed_at = timezone.now()
            run.save()
            return run
    
    def _process_discoveries(
        self,
        discovered: list[DiscoveredAgent],
        source_id: str,
    ) -> list[AgentSubmission]:
        """
        Process discovered agents: filter, deduplicate, and create submissions.
        
        Filtering steps:
        1. URL classification (blocked, aggregator, github, non_root, normal)
        2. Skip blocked URLs
        3. Deduplicate against existing agents/submissions
        4. Create submissions with appropriate flags
        
        Args:
            discovered: List of discovered agents
            source_id: ID of the source (for audit)
            
        Returns:
            List of newly created AgentSubmission records
        """
        if not discovered:
            return []
        
        # Get existing URLs for deduplication
        existing_urls = self._get_existing_urls()
        
        # Track statistics
        blocked_count = 0
        duplicate_count = 0
        
        # Filter and classify URLs
        filtered_discoveries: list[tuple[DiscoveredAgent, str]] = []
        
        for agent in discovered:
            # Classify the URL
            classification = get_url_classification(agent.website)
            
            # Skip blocked URLs
            if classification == "blocked":
                reason = get_block_reason(agent.website)
                logger.debug(f"Blocked URL: {agent.website} - {reason}")
                blocked_count += 1
                continue
            
            # Check for duplicates
            normalized = normalize_url(agent.website)
            if not normalized or normalized in existing_urls:
                duplicate_count += 1
                continue
            
            # Add to set to avoid duplicates within this batch
            existing_urls.add(normalized)
            filtered_discoveries.append((agent, classification))
        
        logger.info(
            f"URL filtering: {len(discovered)} discovered, "
            f"{blocked_count} blocked, {duplicate_count} duplicates, "
            f"{len(filtered_discoveries)} to create"
        )
        
        # Create submissions for filtered discoveries
        submissions = []
        with transaction.atomic():
            for agent, classification in filtered_discoveries:
                try:
                    # Determine if needs manual review based on classification
                    needs_review = classification in ("non_root", "github")
                    
                    # Build enrichment metadata based on classification
                    enrichment_meta = {
                        "url_classification": classification,
                        "source_id": source_id,
                    }
                    
                    if classification == "aggregator":
                        enrichment_meta["is_aggregator"] = True
                        enrichment_meta["needs_url_extraction"] = True
                    
                    if classification == "github":
                        enrichment_meta["is_github"] = True
                        enrichment_meta["potential_open_source"] = True
                    
                    submission = AgentSubmission.objects.create(
                        agent_name=agent.name[:200],
                        agent_website=agent.website[:255],
                        agent_description=agent.description or f"Discovered from {source_id}",
                        source=SubmissionSource.AUTO,
                        status=SubmissionStatus.PENDING,
                        needs_manual_review=needs_review,
                        # Store classification metadata in enrichment_data
                        # (will be expanded during actual enrichment)
                        enrichment_data={"_sourcing_metadata": enrichment_meta},
                    )
                    submissions.append(submission)
                    
                    if classification != "normal":
                        logger.debug(
                            f"Created submission [{classification}]: "
                            f"{agent.name} - {agent.website}"
                        )
                        
                except Exception as e:
                    logger.warning(f"Failed to create submission for {agent.website}: {e}")
                    continue
        
        logger.info(f"Created {len(submissions)} new submissions")
        return submissions
    
    def _get_existing_urls(self) -> set[str]:
        """
        Get normalized URLs of all existing agents and pending submissions.
        
        Returns:
            Set of normalized URLs
        """
        urls = set()
        
        # Published agents
        for website in Agent.objects.values_list("website", flat=True):
            normalized = normalize_url(website)
            if normalized:
                urls.add(normalized)
        
        # Pending/approved submissions (not rejected)
        for website in AgentSubmission.objects.exclude(
            status=SubmissionStatus.REJECTED
        ).values_list("agent_website", flat=True):
            normalized = normalize_url(website)
            if normalized:
                urls.add(normalized)
        
        logger.debug(f"Found {len(urls)} existing URLs for deduplication")
        return urls
    
    def _enrich_submissions(self, submissions: list[AgentSubmission]) -> None:
        """
        Trigger enrichment for new submissions.
        
        Args:
            submissions: List of submissions to enrich
        """
        from aiagents_directory.auto_directory.services.enrichment import EnrichmentService
        
        logger.info(f"Auto-enriching {len(submissions)} submissions")
        
        service = EnrichmentService()
        
        for submission in submissions:
            try:
                service.enrich_submission(submission)
            except Exception as e:
                logger.warning(
                    f"Failed to enrich submission {submission.pk} "
                    f"({submission.agent_name}): {e}"
                )
    
    def get_source_ids(self) -> list[str]:
        """Get list of registered source IDs."""
        return [s.source_id for s in self.sources]
    
    def add_source(self, source: BaseSource) -> None:
        """
        Add a source to the service.
        
        Args:
            source: Source instance to add
        """
        # Avoid duplicates
        if source.source_id not in self.get_source_ids():
            self.sources.append(source)
