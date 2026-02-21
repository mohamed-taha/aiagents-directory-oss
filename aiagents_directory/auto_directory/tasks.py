"""
Celery tasks for the auto_directory pipeline.

Tasks for:
- Agent enrichment (enrich_agent_task, enrich_submission_task)
- Agent sourcing (daily_sourcing_task, source_agents_task)
"""

import logging
from typing import TYPE_CHECKING

from celery import shared_task

from aiagents_directory.agents.models import Agent, AgentSubmission
from aiagents_directory.auto_directory.services import EnrichmentService

if TYPE_CHECKING:
    from aiagents_directory.auto_directory.models import SourcingRun

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def enrich_agent_task(self, agent_id: int, fields: list[str] | None = None) -> dict:
    """
    Celery task to enrich a single agent.
    
    Args:
        agent_id: ID of the agent to enrich
        fields: Optional list of fields to update
        
    Returns:
        Dict with task result info
    """
    logger.info(f"Starting enrichment task for agent_id: {agent_id}")
    
    try:
        agent = Agent.objects.get(id=agent_id)
        service = EnrichmentService()
        log = service.enrich_agent(agent, fields=fields)
        
        return {
            "success": log.success,
            "agent_id": agent_id,
            "agent_name": agent.name,
            "applied_fields": log.applied_fields,
            "error_message": log.error_message,
        }
        
    except Agent.DoesNotExist:
        logger.error(f"Agent {agent_id} not found")
        return {"success": False, "error": f"Agent {agent_id} not found"}
        
    except Exception as e:
        logger.error(f"Enrichment task failed for agent {agent_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=2)
def enrich_submission_task(self, submission_id: int) -> dict:
    """
    Celery task to enrich a single submission.
    
    Args:
        submission_id: ID of the submission to enrich
        
    Returns:
        Dict with task result info
    """
    logger.info(f"Starting enrichment task for submission_id: {submission_id}")
    
    try:
        submission = AgentSubmission.objects.get(id=submission_id)
        service = EnrichmentService()
        service.enrich_submission(submission)
        
        # Check if enrichment succeeded
        enrichment_data = submission.enrichment_data or {}
        success = enrichment_data.get("success", False)
        
        return {
            "success": success,
            "submission_id": submission_id,
            "agent_name": submission.agent_name,
            "error_message": enrichment_data.get("error_message"),
        }
        
    except AgentSubmission.DoesNotExist:
        logger.error(f"Submission {submission_id} not found")
        return {"success": False, "error": f"Submission {submission_id} not found"}
        
    except Exception as e:
        logger.error(f"Enrichment task failed for submission {submission_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


@shared_task
def enrich_agents_batch_task(agent_ids: list[int], fields: list[str] | None = None) -> dict:
    """
    Celery task to enrich multiple agents.
    
    Args:
        agent_ids: List of agent IDs to enrich
        fields: Optional list of fields to update
        
    Returns:
        Dict with batch results summary
    """
    logger.info(f"Starting batch enrichment for {len(agent_ids)} agents")
    
    service = EnrichmentService()
    agents = Agent.objects.filter(id__in=agent_ids)
    logs = service.enrich_agents(list(agents), fields=fields)
    
    succeeded = sum(1 for log in logs if log.success)
    failed = len(logs) - succeeded
    
    return {
        "total": len(logs),
        "succeeded": succeeded,
        "failed": failed,
        "agent_ids": agent_ids,
    }


# ─────────────────────────────────────────────────────────────
# Sourcing Task
# ─────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2)
def source_agents_task(
    self,
    limit: int = 50,
    auto_enrich: bool = True,
    auto_review: bool = False,
    queries: list[str] | None = None,
    use_daily_queries: bool = False,
    tbs: str | None = None,
) -> dict:
    """
    Celery task to run SERP sourcing.
    
    Used for both scheduled (daily) and ad-hoc sourcing.
    
    Args:
        limit: Maximum agents to discover
        auto_enrich: Whether to auto-enrich discovered agents
        auto_review: Whether to auto-review after enrichment
        queries: Custom search queries (overrides use_daily_queries)
        use_daily_queries: If True, use rotating daily queries instead of all
        tbs: Time-based search filter.
             Options: "qdr:d" (day), "qdr:w" (week), "qdr:m" (month), None (all time)
        
    Returns:
        Dict with sourcing results
    """
    from aiagents_directory.auto_directory.services import SourcingService
    from aiagents_directory.auto_directory.sources import SerpSource
    from aiagents_directory.auto_directory.sources.queries import get_daily_queries
    
    logger.info(f"Starting source_agents_task: limit={limit}, tbs={tbs}")
    
    try:
        # Determine queries
        if queries:
            source_queries = queries
        elif use_daily_queries:
            source_queries = get_daily_queries()
            logger.info(f"Using daily rotating queries: {source_queries}")
        else:
            source_queries = None  # Uses all queries via default
        
        source = SerpSource(queries=source_queries, tbs=tbs)
        service = SourcingService(sources=[source])
        
        runs = service.run_all(
            limit_per_source=limit,
            auto_enrich=auto_enrich,
        )
        
        run = runs[0] if runs else None
        
        if not run:
            return {"success": False, "error": "No run created"}
        
        result = {
            "success": run.success,
            "source_id": run.source_id,
            "discovered_count": run.discovered_count,
            "new_count": run.new_count,
            "skipped_count": run.skipped_count,
            "error_message": run.error_message,
            "created_submission_ids": run.created_submission_ids,
        }
        
        logger.info(
            f"Sourcing complete: discovered={run.discovered_count}, "
            f"new={run.new_count}, skipped={run.skipped_count}"
        )
        
        # Optionally run review after enrichment
        if auto_review and run.new_count > 0 and run.created_submission_ids:
            review_submissions_batch_task.delay(run.created_submission_ids)
            result["review_queued"] = len(run.created_submission_ids)
        
        return result
        
    except Exception as e:
        logger.error(f"source_agents_task failed: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


@shared_task
def review_submissions_batch_task(submission_ids: list[int], auto_apply: bool = False) -> dict:
    """
    Celery task to review multiple submissions.
    
    Args:
        submission_ids: List of submission IDs to review
        auto_apply: Whether to auto-apply review decisions
        
    Returns:
        Dict with review results summary
    """
    from aiagents_directory.auto_directory.services.review import ReviewService
    
    logger.info(f"Starting batch review for {len(submission_ids)} submissions")
    
    service = ReviewService()
    results = {"approved": 0, "rejected": 0, "needs_review": 0, "errors": 0}
    
    for submission_id in submission_ids:
        try:
            submission = AgentSubmission.objects.get(id=submission_id)
            
            # Only review if enriched
            if not submission.enrichment_data:
                logger.warning(f"Skipping review for {submission_id}: no enrichment data")
                continue
            
            submission = service.review_submission(submission, auto_apply=auto_apply)
            
            # Track results
            review_result = submission.ai_review_result or {}
            decision = review_result.get("decision", "needs_review")
            
            if decision == "approved":
                results["approved"] += 1
            elif decision == "rejected":
                results["rejected"] += 1
            else:
                results["needs_review"] += 1
                
        except AgentSubmission.DoesNotExist:
            logger.error(f"Submission {submission_id} not found")
            results["errors"] += 1
        except Exception as e:
            logger.error(f"Review failed for submission {submission_id}: {e}")
            results["errors"] += 1
    
    logger.info(f"Batch review complete: {results}")
    return results
