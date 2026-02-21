"""
Management command to enrich agents from their websites.

Usage:
    # Enrich all agents
    python manage.py enrich_agents

    # Enrich specific agents by ID
    python manage.py enrich_agents --agent-ids 1 2 3

    # Enrich specific agents by slug
    python manage.py enrich_agents --slugs my-agent another-agent

    # Enrich only specific fields
    python manage.py enrich_agents --fields logo description pricing_model

    # Limit number of agents
    python manage.py enrich_agents --limit 10

    # Add delay between agents (rate limiting)
    python manage.py enrich_agents --delay 2
"""

import logging
import time
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import QuerySet

from aiagents_directory.agents.models import Agent
from aiagents_directory.auto_directory.services import (
    ENRICHABLE_FIELDS,
    EnrichmentService,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Enrich agents with data from their websites using Firecrawl"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--agent-ids",
            type=int,
            nargs="+",
            help="Specific agent IDs to enrich",
        )
        parser.add_argument(
            "--slugs",
            type=str,
            nargs="+",
            help="Specific agent slugs to enrich",
        )
        parser.add_argument(
            "--exclude-ids",
            type=int,
            nargs="+",
            help="Agent IDs to exclude",
        )
        parser.add_argument(
            "--fields",
            type=str,
            nargs="+",
            choices=list(ENRICHABLE_FIELDS),
            help=f"Fields to enrich. Choices: {', '.join(sorted(ENRICHABLE_FIELDS))}",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of agents to process",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Delay in seconds between agents (default: 1.0)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def get_agents(self, **options: Any) -> QuerySet[Agent]:
        """Build queryset based on command options."""
        agents = Agent.objects.all()

        if options["agent_ids"]:
            agents = agents.filter(id__in=options["agent_ids"])
            self.stdout.write(f"Filtering by IDs: {options['agent_ids']}")

        if options["slugs"]:
            agents = agents.filter(slug__in=options["slugs"])
            self.stdout.write(f"Filtering by slugs: {options['slugs']}")

        if options["exclude_ids"]:
            agents = agents.exclude(id__in=options["exclude_ids"])
            self.stdout.write(f"Excluding IDs: {options['exclude_ids']}")

        # Only agents with websites
        agents = agents.exclude(website="").exclude(website__isnull=True)

        if options["limit"]:
            agents = agents[: options["limit"]]
            self.stdout.write(f"Limited to {options['limit']} agents")

        return agents

    def handle(self, *args: Any, **options: Any) -> None:
        agents = self.get_agents(**options)
        total = agents.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No agents found to enrich"))
            return

        fields = options["fields"]
        delay = options["delay"]
        dry_run = options["dry_run"]

        self.stdout.write(
            self.style.SUCCESS(f"\nEnriching {total} agent(s)")
        )
        if fields:
            self.stdout.write(f"Fields: {', '.join(fields)}")
        else:
            self.stdout.write("Fields: all")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] No changes will be made\n"))
            for agent in agents:
                self.stdout.write(f"  Would enrich: {agent.name} ({agent.website})")
            return

        service = EnrichmentService()
        succeeded = 0
        failed = 0

        for i, agent in enumerate(agents, 1):
            self.stdout.write(f"\n[{i}/{total}] Enriching: {agent.name}")
            self.stdout.write(f"  Website: {agent.website}")

            try:
                log = service.enrich_agent(agent, fields=fields)

                if log.success:
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Success: {', '.join(log.applied_fields) or 'no changes'}")
                    )
                    succeeded += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ Failed: {log.error_message}")
                    )
                    failed += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
                failed += 1
                logger.exception(f"Failed to enrich {agent.name}")

            # Delay between agents
            if i < total and delay > 0:
                time.sleep(delay)

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"Completed: {succeeded} succeeded, {failed} failed"))

