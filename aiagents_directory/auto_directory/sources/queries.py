"""
Search queries for agent sourcing.

Query Types:
- BASIC: Core AI agent terms (evergreen)
- CATEGORIES: By vertical (coding, sales, marketing, etc.)  
- TRENDING: Catch new launches, funding, buzz

Usage:
    # Get all queries for seeding
    queries = get_queries("all")
    
    # Get queries by type
    queries = get_queries("basic")
    queries = get_queries("trending")
    queries = get_queries("category", category="coding")
    
    # Daily rotation (different categories each day)
    queries = get_daily_queries()
"""

from datetime import datetime


# ─────────────────────────────────────────────────────────────
# BASIC - Core AI agent terms (evergreen)
# ─────────────────────────────────────────────────────────────

BASIC = [
    "AI agent tool",
    "AI agent software", 
    "AI agent platform",
    "autonomous AI agent",
    "AI automation agent",
    "LLM agent",
    "AI digital worker",
]


# ─────────────────────────────────────────────────────────────
# CATEGORIES - By vertical
# ─────────────────────────────────────────────────────────────

CATEGORIES = {
    "coding": [
        "AI coding agent",
        "AI developer assistant",
        "AI pair programming",
        "AI code generation agent",
    ],
    "sales": [
        "AI sales agent",
        "AI SDR agent", 
        "AI lead generation agent",
        "AI outbound agent",
    ],
    "marketing": [
        "AI marketing agent",
        "AI content marketing agent",
        "AI SEO agent",
        "AI social media agent",
    ],
    "customer_support": [
        "AI customer support agent",
        "AI helpdesk agent",
        "AI chatbot agent",
    ],
    "research": [
        "AI research agent",
        "AI research assistant",
        "AI data analysis agent",
    ],
    "writing": [
        "AI writing agent",
        "AI copywriting agent",
        "AI content creation agent",
    ],
    "productivity": [
        "AI scheduling agent",
        "AI workflow agent",
        "AI personal assistant agent",
    ],
    "hr": [
        "AI recruiting agent",
        "AI hiring agent",
        "AI HR agent",
    ],
    "finance": [
        "AI finance agent",
        "AI accounting agent",
        "AI trading agent",
    ],
    "legal": [
        "AI legal agent",
        "AI contract agent",
    ],
    "data": [
        "AI data agent",
        "AI web scraping agent",
        "AI data extraction agent",
    ],
}


# ─────────────────────────────────────────────────────────────
# TRENDING - Catch new launches, funding, buzz
# ─────────────────────────────────────────────────────────────

def _get_trending() -> list[str]:
    """Get trending queries with current year."""
    year = datetime.now().year
    return [
        f"new AI agent {year}",
        f"AI agent launched {year}",
        f"best AI agents {year}",
        "AI agent startup funding",
        "AI agent product launch",
        "emerging AI agents",
        "AI agents to watch",
    ]


TRENDING = _get_trending()


# ─────────────────────────────────────────────────────────────
# Query Functions
# ─────────────────────────────────────────────────────────────

def get_queries(
    query_type: str = "all",
    category: str | None = None,
) -> list[str]:
    """
    Get queries by type.
    
    Args:
        query_type: "basic", "trending", "category", or "all"
        category: Required if query_type is "category"
        
    Returns:
        List of search queries
        
    Examples:
        get_queries("basic")
        get_queries("trending")
        get_queries("category", category="coding")
        get_queries("all")
    """
    if query_type == "basic":
        return BASIC.copy()
    
    elif query_type == "trending":
        return _get_trending()
    
    elif query_type == "category":
        if category and category in CATEGORIES:
            return CATEGORIES[category].copy()
        return []
    
    elif query_type == "all":
        queries = []
        queries.extend(BASIC)
        queries.extend(_get_trending())
        for cat_queries in CATEGORIES.values():
            queries.extend(cat_queries)
        return _dedupe(queries)
    
    return []


def get_category_queries(category: str) -> list[str]:
    """Get queries for a specific category."""
    return CATEGORIES.get(category, []).copy()


def get_all_categories() -> list[str]:
    """Get list of available categories."""
    return list(CATEGORIES.keys())


def get_daily_queries(day: int | None = None) -> list[str]:
    """
    Get queries for daily rotation.
    
    Rotates through categories by day of week.
    Always includes trending queries.
    
    Args:
        day: 0=Monday, 6=Sunday. None=today.
        
    Returns:
        Queries for that day
    """
    if day is None:
        day = datetime.now().weekday()
    
    # Rotate categories across the week
    categories = list(CATEGORIES.keys())
    
    # 2 categories per day (11 categories / 6 days ≈ 2)
    cats_per_day = 2
    start = (day * cats_per_day) % len(categories)
    day_categories = categories[start:start + cats_per_day]
    
    # Handle wrap-around
    if start + cats_per_day > len(categories):
        day_categories += categories[:cats_per_day - len(day_categories)]
    
    # Build queries: trending + category queries
    queries = _get_trending()[:3]  # Top 3 trending
    for cat in day_categories:
        queries.extend(CATEGORIES[cat][:2])  # Top 2 per category
    
    return queries


def get_stats() -> dict:
    """Get query statistics."""
    all_queries = get_queries("all")
    return {
        "total": len(all_queries),
        "basic": len(BASIC),
        "trending": len(_get_trending()),
        "categories": {k: len(v) for k, v in CATEGORIES.items()},
    }


def _dedupe(queries: list[str]) -> list[str]:
    """Remove duplicates while preserving order."""
    seen: set[str] = set()
    result = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            result.append(q)
    return result
