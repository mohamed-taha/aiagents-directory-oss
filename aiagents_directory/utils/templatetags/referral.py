"""
Template tags for adding referral tracking to outbound URLs.

Uses a simple ref parameter (industry standard for directory referrals).
"""
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from django import template
from django.conf import settings

register = template.Library()


@register.filter
def add_referral(url: str) -> str:
    """
    Add referral parameter to an outbound URL.
    
    Standard format: ?ref=aiagentsdirectory
    
    Args:
        url: The URL to add referral parameter to
        
    Returns:
        URL with ref parameter appended
        
    Example:
        {{ agent.website|add_referral }}
        # Returns: https://example.com?ref=aiagentsdirectory
    """
    if not url:
        return url
    
    # Skip if it's not an HTTP/HTTPS URL
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return url
    
    # Get referral source from settings (default to site name)
    ref_source = getattr(settings, 'REFERRAL_SOURCE', 'aiagentsdirectory')
    
    # Parse existing query parameters
    query_params = parse_qs(parsed.query)
    
    # Add ref parameter (don't override if it already exists)
    if 'ref' not in query_params:
        query_params['ref'] = [ref_source]
    
    # Rebuild URL with new parameters
    new_query = urlencode(query_params, doseq=True)
    new_parsed = parsed._replace(query=new_query)
    
    return urlunparse(new_parsed)

