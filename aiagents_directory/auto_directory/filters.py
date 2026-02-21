"""
URL filtering and classification for agent sourcing.

This module provides functions to classify URLs and determine how they should
be handled during the sourcing and enrichment pipeline.

Classifications:
- blocked: URL should be rejected (templates, papers, news sites)
- aggregator: URL is from a directory/aggregator - need to extract real product URL
- github: Valid for open source projects, needs special handling
- allowlist: Known valid big tech agent URLs
- non_root: Has path beyond root domain - flag for review
- normal: Standard URL, process normally
"""

import re
from typing import Literal
from urllib.parse import urlparse

from django.conf import settings


# Type for URL classifications
URLClassification = Literal[
    "blocked", "aggregator", "github", "allowlist", "non_root", "normal"
]


def _get_domain(url: str) -> str:
    """Extract domain from URL, removing www prefix."""
    if not url:
        return ""
    
    try:
        parsed = urlparse(url.lower().strip())
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _get_path(url: str) -> str:
    """Extract path from URL."""
    if not url:
        return ""
    
    try:
        parsed = urlparse(url.lower().strip())
        return parsed.path
    except Exception:
        return ""


def _domain_matches(domain: str, pattern: str) -> bool:
    """
    Check if domain matches pattern.
    
    Supports:
    - Exact match: "example.com"
    - Subdomain match: "*.example.com" matches "sub.example.com"
    """
    if not domain or not pattern:
        return False
    
    pattern = pattern.lower()
    domain = domain.lower()
    
    if pattern.startswith("*."):
        # Wildcard subdomain match
        base = pattern[2:]
        return domain == base or domain.endswith("." + base)
    else:
        # Exact match or subdomain of pattern
        return domain == pattern or domain.endswith("." + pattern)


def is_blocked_url(url: str) -> bool:
    """
    Check if URL should be blocked (rejected during sourcing).
    
    Checks against:
    1. Domain blocklist (from settings)
    2. Path blocklist patterns (from settings) - BUT skipped for aggregator domains
    
    Note: Aggregator domains (YC, ProductHunt, etc.) are exempt from path blocklist
    since they have paths like /companies/ that we want to extract from, not block.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL should be blocked
    """
    domain = _get_domain(url)
    path = _get_path(url)
    
    # Check domain blocklist first
    blocklist = getattr(settings, "AUTO_DIRECTORY_DOMAIN_BLOCKLIST", [])
    for blocked_domain in blocklist:
        if _domain_matches(domain, blocked_domain):
            return True
    
    # Skip path blocklist check for aggregator domains
    # (we want to extract URLs from these, not block them)
    aggregator_domains = getattr(settings, "AUTO_DIRECTORY_AGGREGATOR_DOMAINS", [])
    for agg_domain in aggregator_domains:
        if _domain_matches(domain, agg_domain):
            return False  # Not blocked - will be handled as aggregator
    
    # Check path blocklist for non-aggregator URLs
    path_blocklist = getattr(settings, "AUTO_DIRECTORY_PATH_BLOCKLIST", [])
    for blocked_path in path_blocklist:
        blocked_path = blocked_path.lower()
        if blocked_path in path:
            return True
    
    return False


def is_aggregator_url(url: str) -> bool:
    """
    Check if URL is from an aggregator/directory site.
    
    These URLs need special handling - we should extract the actual
    product URL from the page during enrichment.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is from an aggregator site
    """
    domain = _get_domain(url)
    
    aggregator_domains = getattr(settings, "AUTO_DIRECTORY_AGGREGATOR_DOMAINS", [])
    for agg_domain in aggregator_domains:
        if _domain_matches(domain, agg_domain):
            return True
    
    return False


def is_github_url(url: str) -> bool:
    """
    Check if URL is a GitHub URL.
    
    GitHub URLs are valid for open source projects and get special handling.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is from GitHub
    """
    domain = _get_domain(url)
    return domain in ("github.com", "github.io") or domain.endswith(".github.io")


def is_allowlisted_url(url: str) -> bool:
    """
    Check if URL is in the allowlist (known valid agent URLs).
    
    These are pre-approved domains that don't need extra validation.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is allowlisted
    """
    domain = _get_domain(url)
    
    allowlist = getattr(settings, "AUTO_DIRECTORY_DOMAIN_ALLOWLIST", [])
    for allowed_domain in allowlist:
        if _domain_matches(domain, allowed_domain):
            return True
    
    return False


def is_non_root_url(url: str) -> bool:
    """
    Check if URL has a significant path (not just root domain).
    
    Non-root URLs like example.com/product/agent are flagged for review
    since they might be subpages rather than the main product.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL has path beyond root
    """
    path = _get_path(url)
    
    # Remove trailing slash and check if there's meaningful path
    path = path.rstrip("/")
    
    # Ignore common root paths
    root_paths = ("", "/", "/en", "/en-us", "/en-gb")
    
    if path.lower() in root_paths:
        return False
    
    # Check if path has content (beyond just language codes)
    # A non-root path has at least one segment
    segments = [s for s in path.split("/") if s]
    
    return len(segments) > 0


def get_url_classification(url: str) -> URLClassification:
    """
    Get the classification for a URL.
    
    Order of precedence:
    1. Blocked (reject immediately)
    2. Aggregator (needs URL extraction)
    3. GitHub (valid for open source)
    4. Allowlist (pre-approved)
    5. Non-root (flag for review)
    6. Normal (process normally)
    
    Args:
        url: URL to classify
        
    Returns:
        Classification string
    """
    # Check in order of precedence
    if is_blocked_url(url):
        return "blocked"
    
    if is_aggregator_url(url):
        return "aggregator"
    
    if is_github_url(url):
        # Check if GitHub is enabled
        github_valid = getattr(settings, "AUTO_DIRECTORY_GITHUB_VALID", True)
        if github_valid:
            return "github"
        else:
            return "blocked"
    
    if is_allowlisted_url(url):
        return "allowlist"
    
    if is_non_root_url(url):
        return "non_root"
    
    return "normal"


def get_block_reason(url: str) -> str | None:
    """
    Get a human-readable reason why a URL was blocked.
    
    Args:
        url: URL to check
        
    Returns:
        Reason string if blocked, None otherwise
    """
    domain = _get_domain(url)
    path = _get_path(url)
    
    # Check domain blocklist
    blocklist = getattr(settings, "AUTO_DIRECTORY_DOMAIN_BLOCKLIST", [])
    for blocked_domain in blocklist:
        if _domain_matches(domain, blocked_domain):
            return f"Domain '{blocked_domain}' is in blocklist"
    
    # Check path blocklist
    path_blocklist = getattr(settings, "AUTO_DIRECTORY_PATH_BLOCKLIST", [])
    for blocked_path in path_blocklist:
        if blocked_path.lower() in path.lower():
            return f"Path contains blocked pattern '{blocked_path}'"
    
    return None


# Convenience function for extraction prompts
AGGREGATOR_URL_EXTRACTION_PROMPT = """
Extract the actual product/company website URL from this directory or aggregator page.

Look for:
- Official website links (usually labeled "Website", "Homepage", "Visit")
- Company domain links in the content
- Links that go to the actual product, not social media or other directories

Return ONLY the main product website URL, not:
- Social media links (twitter, linkedin, etc.)
- Other directory links
- Blog or news article links

If no clear product website is found, return null.
"""


def get_aggregator_extraction_schema() -> dict:
    """
    Get the JSON schema for extracting real URLs from aggregator pages.
    
    Returns:
        JSON schema dict for Firecrawl extraction
    """
    return {
        "type": "object",
        "properties": {
            "product_website": {
                "type": "string",
                "description": "The official website URL of the product/company",
            },
            "product_name": {
                "type": "string",
                "description": "The name of the product",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score 0-1 that this is the correct URL",
            },
        },
        "required": ["product_website"],
    }

