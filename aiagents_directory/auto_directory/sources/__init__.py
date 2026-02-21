"""
Source plugins for automated agent discovery.

This module provides a plugin-based architecture for discovering AI agents
from various sources.

Available sources:
- SerpSource: Discovers agents via Firecrawl search API

Query utilities:
- queries: Query sets for seeding and ongoing discovery
"""

from aiagents_directory.auto_directory.sources.base import (
    BaseSource,
    DiscoveredAgent,
    normalize_url,
)
from aiagents_directory.auto_directory.sources.serp import SerpSource

__all__ = [
    "BaseSource",
    "DiscoveredAgent",
    "normalize_url",
    "SerpSource",
]
