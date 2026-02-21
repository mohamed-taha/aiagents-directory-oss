"""
Base classes and protocols for source plugins.

This module defines the interface that all source plugins must implement,
along with the DiscoveredAgent dataclass for representing discovered agents.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class DiscoveredAgent:
    """
    Represents an agent discovered from a source.
    
    This is a lightweight data transfer object used to pass discovered
    agent information from sources to the SourcingService.
    
    Attributes:
        name: Name of the agent/product
        website: Website URL of the agent
        description: Brief description (may be empty if not available)
        source_id: ID of the source that discovered this agent
        source_url: URL where this agent was discovered (for audit trail)
        metadata: Optional additional data from the source
    """
    
    name: str
    website: str
    description: str = ""
    source_id: str = ""
    source_url: str = ""
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate and normalize fields after initialization."""
        # Ensure website has a scheme
        if self.website and not self.website.startswith(("http://", "https://")):
            self.website = f"https://{self.website}"
        
        # Strip whitespace
        self.name = self.name.strip()
        self.website = self.website.strip()
        self.description = self.description.strip()


def normalize_url(url: str) -> str:
    """
    Normalize a URL for comparison/deduplication.
    
    Removes protocol, www prefix, and trailing slashes to allow
    matching URLs that point to the same resource.
    
    Examples:
        "https://www.example.com/" -> "example.com"
        "http://example.com" -> "example.com"
        "https://example.com/path/" -> "example.com/path"
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL string
    """
    if not url:
        return ""
    
    # Parse the URL
    parsed = urlparse(url.lower().strip())
    
    # Get host (remove www prefix)
    host = parsed.netloc or parsed.path.split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    
    # Get path (remove trailing slash)
    path = parsed.path.rstrip("/")
    
    # If the path was in netloc (no scheme), adjust
    if not parsed.netloc and "/" in parsed.path:
        parts = parsed.path.split("/", 1)
        host = parts[0]
        if host.startswith("www."):
            host = host[4:]
        path = "/" + parts[1].rstrip("/") if len(parts) > 1 else ""
    
    # Combine host and path
    normalized = host + path
    
    return normalized


class BaseSource(ABC):
    """
    Abstract base class for all source plugins.
    
    Each source must implement:
    - source_id: Unique identifier for this source
    - discover(): Method to discover agents
    - is_available(): Check if the source can be used
    
    Example:
        class MySource(BaseSource):
            source_id = "my_source"
            
            def discover(self, limit: int = 100) -> list[DiscoveredAgent]:
                # ... discovery logic ...
                return agents
            
            def is_available(self) -> bool:
                return True
    """
    
    # Unique identifier for this source (e.g., "serp", "url", "taaft")
    source_id: str = ""
    
    @abstractmethod
    def discover(self, limit: int = 100) -> list[DiscoveredAgent]:
        """
        Discover agents from this source.
        
        Args:
            limit: Maximum number of agents to discover
            
        Returns:
            List of DiscoveredAgent objects
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this source is available and properly configured.
        
        Returns:
            True if the source can be used, False otherwise
        """
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source_id={self.source_id!r}>"
