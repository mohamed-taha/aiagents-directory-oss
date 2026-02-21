"""
SERP (Search Engine Results Page) source plugin.

Discovers AI agents by searching the web using Firecrawl's search API
with intelligent content extraction.

Uses Firecrawl's scrapeOptions with JSON extraction to:
1. Search for AI agent-related queries
2. Scrape each search result (blog posts, directories, listicles)
3. Extract AI agent product information using LLM-powered JSON extraction
4. Return structured agent data

This approach leverages Firecrawl's built-in LLM extraction rather than
manual link filtering.
"""

import logging
from typing import Any

from django.conf import settings
from firecrawl import Firecrawl

from aiagents_directory.auto_directory.sources.base import BaseSource, DiscoveredAgent


logger = logging.getLogger(__name__)


# Default: use all queries for maximum coverage
def _get_default_queries() -> list[str]:
    from aiagents_directory.auto_directory.sources.queries import get_queries
    return get_queries("all")

# JSON schema for extracting AI agents from pages
AI_AGENTS_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "agents": {
            "type": "array",
            "description": "List of AI agent products found on this page",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the AI agent product",
                    },
                    "website": {
                        "type": "string",
                        "description": "Official website URL of the AI agent (not social media or blog links)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the AI agent does",
                    },
                },
                "required": ["name", "website"],
            },
        },
    },
    "required": ["agents"],
}

# Extraction prompt for the LLM
AI_AGENTS_EXTRACTION_PROMPT = """
Extract all AI agent products mentioned on this page. An AI agent is:
- Autonomous software that performs tasks using AI/ML
- Software that can take actions on behalf of users
- AI-powered automation tools with agent-like capabilities
- Platforms for building or running AI agents

For each AI agent found, extract:
- name: The product name
- website: The official product website URL (NOT social media, blog posts, or directory links)
- description: A brief description of what it does

IMPORTANT:
- Only include actual AI agent products, not blog posts or directories
- Skip social media links (twitter, linkedin, etc.)
- Skip generic tools that aren't AI agents
- The website should be the product's homepage (e.g., https://example.com not https://blog.example.com/article)
"""


class SerpSource(BaseSource):
    """
    Source plugin that discovers agents via web search with LLM extraction.
    
    Uses Firecrawl's search API with scrapeOptions to:
    1. Search for AI agent queries
    2. Scrape each result with JSON extraction
    3. Extract AI agent products using LLM
    
    This finds real AI agent products from blog posts, directories, and listicles.
    
    Configuration:
        - queries: List of search queries to use
        - results_per_query: Search results per query (default: 10)
        - extract_agents: Use LLM extraction to find agents (default: True)
        - tbs: Time-based search filter (e.g., "qdr:w" for past week)
        - location: Geo-targeting location (e.g., "United States")
    
    Example:
        source = SerpSource(queries=["AI agent tool"], extract_agents=True)
        agents = source.discover(limit=50)
    """
    
    source_id = "serp"
    
    def __init__(
        self,
        queries: list[str] | None = None,
        results_per_query: int = 10,
        extract_agents: bool = True,
        tbs: str | None = None,
        location: str | None = None,
    ) -> None:
        """
        Initialize the SERP source.
        
        Args:
            queries: List of search queries (defaults to DEFAULT_SEARCH_QUERIES)
            results_per_query: Search results per query (each is scraped for agents)
            extract_agents: If True, use LLM extraction to find agents in results.
                           If False, use search results directly (less accurate).
            tbs: Time-based search filter. Options:
                 - "qdr:h" = past hour
                 - "qdr:d" = past 24 hours
                 - "qdr:w" = past week
                 - "qdr:m" = past month
                 - "qdr:y" = past year
            location: Geo-targeting location (e.g., "United States", "Germany")
        """
        self.queries = queries or _get_default_queries()
        self.results_per_query = results_per_query
        self.extract_agents = extract_agents
        self.tbs = tbs
        self.location = location
        self._client: Firecrawl | None = None
    
    @property
    def client(self) -> Firecrawl:
        """Lazy-load the Firecrawl client."""
        if self._client is None:
            api_key = getattr(settings, "FIRECRAWL_API_KEY", None)
            if not api_key:
                raise ValueError("FIRECRAWL_API_KEY not configured in settings")
            self._client = Firecrawl(api_key=api_key)
        return self._client
    
    def is_available(self) -> bool:
        """Check if Firecrawl API is configured."""
        return bool(getattr(settings, "FIRECRAWL_API_KEY", None))
    
    def discover(self, limit: int = 100) -> list[DiscoveredAgent]:
        """
        Discover agents by searching the web.
        
        When extract_agents=True:
        1. Search for AI agent queries
        2. Scrape each result with JSON extraction
        3. Extract AI agent products from content
        
        Args:
            limit: Maximum total number of agents to discover
            
        Returns:
            List of discovered agents
        """
        if not self.is_available():
            logger.warning("SerpSource: Firecrawl API key not configured")
            return []
        
        discovered: list[DiscoveredAgent] = []
        seen_urls: set[str] = set()
        
        for query in self.queries:
            if len(discovered) >= limit:
                break
            
            try:
                agents_from_query = self._search_and_extract(query)
                
                for agent in agents_from_query:
                    if len(discovered) >= limit:
                        break
                    
                    # Normalize URL for deduplication
                    url = agent.website.lower().rstrip("/")
                    if url in seen_urls:
                        continue
                    
                    seen_urls.add(url)
                    discovered.append(agent)
                    
            except Exception as e:
                logger.error(f"SerpSource: Search failed for query '{query}': {e}")
                continue
        
        logger.info(
            f"SerpSource: Discovered {len(discovered)} agents "
            f"from {len(self.queries)} queries"
        )
        return discovered
    
    def _search_and_extract(self, query: str) -> list[DiscoveredAgent]:
        """
        Search and extract agents from results.
        
        Args:
            query: Search query string
            
        Returns:
            List of DiscoveredAgent from search results
        """
        logger.debug(f"SerpSource: Searching for '{query}'")
        
        if self.extract_agents:
            return self._search_with_extraction(query)
        else:
            return self._search_direct(query)
    
    def _search_with_extraction(self, query: str) -> list[DiscoveredAgent]:
        """
        Search with LLM-powered agent extraction.
        
        Uses Firecrawl's scrapeOptions with JSON format to extract
        AI agent products from each search result.
        """
        try:
            # Build search parameters
            search_params: dict[str, Any] = {
                "query": query,
                "limit": self.results_per_query,
                "scrape_options": {
                    "formats": [
                        {
                            "type": "json",
                            "schema": AI_AGENTS_EXTRACTION_SCHEMA,
                            "prompt": AI_AGENTS_EXTRACTION_PROMPT,
                        }
                    ],
                    "onlyMainContent": True,
                },
            }
            
            # Add optional parameters
            if self.tbs:
                search_params["tbs"] = self.tbs
            if self.location:
                search_params["location"] = self.location
            
            response = self.client.search(**search_params)
            
            if response is None:
                return []
            
            # Extract results from response
            results = self._extract_results(response)
            
            discovered: list[DiscoveredAgent] = []
            
            for result in results:
                source_url = result.get("url", "")
                source_title = result.get("title", "")
                
                # Get extracted JSON data
                json_data = result.get("json", {})
                if not json_data:
                    # Try alternative keys
                    json_data = result.get("extract", result.get("data", {}))
                
                # Get agents from extracted data
                agents = json_data.get("agents", [])
                
                if not agents:
                    logger.debug(f"SerpSource: No agents extracted from {source_url}")
                    continue
                
                logger.debug(
                    f"SerpSource: Extracted {len(agents)} agents from {source_url}"
                )
                
                # Create DiscoveredAgent for each extracted agent
                for agent_data in agents:
                    name = agent_data.get("name", "").strip()
                    website = agent_data.get("website", "").strip()
                    description = agent_data.get("description", "").strip()
                    
                    # Skip invalid entries
                    if not name or not website:
                        continue
                    
                    # Basic URL validation
                    if not website.startswith(("http://", "https://")):
                        website = f"https://{website}"
                    
                    agent = DiscoveredAgent(
                        name=name,
                        website=website,
                        description=description,
                        source_id=self.source_id,
                        source_url=source_url,
                        metadata={
                            "query": query,
                            "found_in": source_title,
                            "extraction_method": "json",
                        },
                    )
                    discovered.append(agent)
            
            logger.debug(
                f"SerpSource: Total {len(discovered)} agents from '{query}'"
            )
            return discovered
            
        except Exception as e:
            logger.error(
                f"SerpSource: Search with extraction failed: {e}",
                exc_info=True
            )
            raise
    
    def _search_direct(self, query: str) -> list[DiscoveredAgent]:
        """
        Search and use results directly (fallback mode).
        
        Does not use LLM extraction - uses search results as-is.
        """
        try:
            # Build search parameters
            search_params: dict[str, Any] = {
                "query": query,
                "limit": self.results_per_query,
            }
            
            if self.tbs:
                search_params["tbs"] = self.tbs
            if self.location:
                search_params["location"] = self.location
            
            response = self.client.search(**search_params)
            
            if response is None:
                return []
            
            results = self._extract_results(response)
            
            discovered: list[DiscoveredAgent] = []
            for result in results:
                url = result.get("url", "")
                if not url:
                    continue
                
                agent = DiscoveredAgent(
                    name=result.get("title", "Unknown"),
                    website=url,
                    description=result.get("description", ""),
                    source_id=self.source_id,
                    source_url=f"search:{query}",
                    metadata={
                        "query": query,
                        "position": result.get("position"),
                        "extraction_method": "direct",
                    },
                )
                discovered.append(agent)
            
            return discovered
            
        except Exception as e:
            logger.error(f"SerpSource: Direct search failed: {e}", exc_info=True)
            raise
    
    def _extract_results(self, response: Any) -> list[dict[str, Any]]:
        """Extract results list from Firecrawl response."""
        # Handle response - can be dict or Pydantic model
        if hasattr(response, "data"):
            data = response.data
        elif isinstance(response, dict):
            data = response.get("data", response)
        else:
            data = response
        
        # Get web results
        if hasattr(data, "web"):
            results = data.web
        elif isinstance(data, dict):
            results = data.get("web", data.get("results", []))
        elif isinstance(data, list):
            results = data
        else:
            results = []
        
        # Convert Pydantic models to dicts
        processed = []
        for r in results:
            if hasattr(r, "model_dump"):
                processed.append(r.model_dump())
            elif hasattr(r, "dict"):
                processed.append(r.dict())
            elif isinstance(r, dict):
                processed.append(r)
        
        return processed
    
    def get_config(self) -> dict:
        """Return configuration used by this source (for audit logging)."""
        return {
            "queries": self.queries,
            "results_per_query": self.results_per_query,
            "extract_agents": self.extract_agents,
            "tbs": self.tbs,
            "location": self.location,
        }
