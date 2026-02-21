"""
Management command to run SERP sourcing.

Usage:
    python manage.py source_agents                    # Default: 50 agents
    python manage.py source_agents --limit=500        # Seed: 500 agents
    python manage.py source_agents --tbs=qdr:w        # Ongoing: past week only
    python manage.py source_agents --auto-enrich
    python manage.py source_agents --dry-run
"""

from django.core.management.base import BaseCommand, CommandParser

from aiagents_directory.auto_directory.services import SourcingService
from aiagents_directory.auto_directory.sources import SerpSource
from aiagents_directory.auto_directory.sources.base import normalize_url


class Command(BaseCommand):
    help = "Run SERP sourcing to discover new AI agents"
    
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum unique agents to discover (default: 50)",
        )
        parser.add_argument(
            "--queries",
            type=str,
            help="Comma-separated search queries (default: all ~47 queries)",
        )
        parser.add_argument(
            "--tbs",
            type=str,
            help="Time filter: qdr:d (day), qdr:w (week), qdr:m (month)",
        )
        parser.add_argument(
            "--auto-enrich",
            action="store_true",
            help="Automatically enrich discovered agents",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Discover agents without creating submissions",
        )
    
    def handle(self, *args, **options) -> None:
        limit = options["limit"]
        auto_enrich = options["auto_enrich"]
        dry_run = options["dry_run"]
        tbs = options.get("tbs")
        
        # Parse queries
        queries = None
        if options.get("queries"):
            queries = [q.strip() for q in options["queries"].split(",")]
        
        # Default: 10 results per query for good coverage
        # Each search can return many relevant pages with agents
        results_per_query = 10
        
        # Build source
        source = SerpSource(
            queries=queries,
            results_per_query=results_per_query,
            tbs=tbs,
        )
        
        self.stdout.write(f"Config: limit={limit}, results_per_query={results_per_query}, tbs={tbs}")
        
        if not source.is_available():
            self.stdout.write(
                self.style.ERROR("SERP source not available (check FIRECRAWL_API_KEY)")
            )
            return
        
        if dry_run:
            self._dry_run(source, limit)
        else:
            self._run_sourcing(source, limit, auto_enrich)
    
    def _dry_run(self, source: SerpSource, limit: int) -> None:
        """Run discovery without creating submissions."""
        self.stdout.write(self.style.WARNING("DRY RUN - no submissions will be created\n"))
        
        discovered = source.discover(limit=limit)
        
        self.stdout.write(f"Discovered {len(discovered)} agents:\n")
        
        for agent in discovered[:20]:
            self.stdout.write(f"  - {agent.name}")
            self.stdout.write(f"    URL: {agent.website}")
            if agent.description:
                desc = agent.description[:100] + "..." if len(agent.description) > 100 else agent.description
                self.stdout.write(f"    Description: {desc}")
        
        if len(discovered) > 20:
            self.stdout.write(f"  ... and {len(discovered) - 20} more")
        
        self.stdout.write(f"\n{self.style.SUCCESS(f'Total: {len(discovered)}')}")
    
    def _run_sourcing(self, source: SerpSource, limit: int, auto_enrich: bool) -> None:
        """Run sourcing and create submissions."""
        service = SourcingService(sources=[source])
        
        runs = service.run_all(
            limit_per_source=limit,
            auto_enrich=auto_enrich,
        )
        
        run = runs[0] if runs else None
        
        if not run:
            self.stdout.write(self.style.ERROR("No run created"))
            return
        
        status = self.style.SUCCESS("✓") if run.success else self.style.ERROR("✗")
        
        self.stdout.write(f"\n{status} Sourcing complete")
        self.stdout.write(f"   Discovered: {run.discovered_count}")
        self.stdout.write(f"   New: {run.new_count}")
        self.stdout.write(f"   Skipped (duplicates): {run.skipped_count}")
        
        if run.error_message:
            self.stdout.write(self.style.ERROR(f"   Error: {run.error_message}"))
        
        if auto_enrich:
            self.stdout.write(self.style.SUCCESS("\nAuto-enrichment triggered"))
