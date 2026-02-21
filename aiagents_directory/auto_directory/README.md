# Auto Directory

Automated pipeline for sourcing, enriching, and reviewing AI agents.

## Pipeline

```
SOURCE → ENRICH → REVIEW → PUBLISH
```

## Sourcing

Discovers AI agents via Firecrawl SERP search.

### Commands

```bash
# Basic
python manage.py source_agents

# With options
python manage.py source_agents --limit=100
python manage.py source_agents --queries="AI coding agent,AI sales agent"
python manage.py source_agents --tbs=qdr:w      # Past week only
python manage.py source_agents --auto-enrich
python manage.py source_agents --dry-run
```

### Time Filters (`--tbs`)

| Value | Filter |
|-------|--------|
| `qdr:d` | Past day |
| `qdr:w` | Past week |
| `qdr:m` | Past month |
| (none) | All time |

### Queries

```python
from aiagents_directory.auto_directory.sources.queries import get_queries, get_daily_queries

get_queries("basic")      # Core terms (7)
get_queries("trending")   # New launches (7)
get_queries("category", category="coding")  # By vertical
get_queries("all")        # Everything (~60)
get_daily_queries()       # Cron: trending + 2 categories
```

### Scheduling

Daily at 6 AM UTC via Celery beat with:
- Rotating queries (2 categories + trending per day)
- Time filter: past week (`tbs=qdr:w`)
- Auto-enrich: enabled

---

## Enrichment

Scrapes agent websites via Firecrawl to extract structured data.

```bash
python manage.py enrich_submissions
python manage.py enrich_submissions --limit=10
python manage.py enrich_submissions --force
```

---

## Review

AI verification using GPT-4o.

```bash
python manage.py review_submissions
python manage.py review_submissions --auto-apply
```

---

## Approval

```bash
python manage.py approve_submissions --dry-run
python manage.py approve_submissions
python manage.py reject_submissions
```

---

## Full Pipeline

```bash
# 1. Discover & enrich
python manage.py source_agents --limit=50 --auto-enrich

# 2. Review
python manage.py review_submissions

# 3. Publish
python manage.py approve_submissions
python manage.py reject_submissions
```

---

## Rollout Plan

### Phase 1: Seed (One-off)

```bash
# Step 1: Discover agents (creates submissions)
python manage.py source_agents --limit=500

# Step 2: Enrich submissions (scrape each agent's website)
python manage.py enrich_submissions

# Step 3: AI Review (verify they're real AI agents)
python manage.py review_submissions

# Step 4: Publish approved, reject others
python manage.py approve_submissions --dry-run   # Preview first
python manage.py approve_submissions             # Create agents
python manage.py reject_submissions              # Clean up
```

**Or combined (source + enrich in one step):**
```bash
python manage.py source_agents --limit=500 --auto-enrich
python manage.py review_submissions
python manage.py approve_submissions
python manage.py reject_submissions
```

**Cost:** ~2,500 Firecrawl credits + ~$5 OpenAI

### Phase 2: Ongoing (Automatic)

Daily at 6 AM UTC via Celery beat. No action needed.

| Step | Automatic |
|------|-----------|
| Source | ✅ (rotating queries, past week) |
| Enrich | ✅ (auto-enrich enabled) |
| Review | ❌ (run manually or enable `auto_review`) |
| Approve | ❌ (run manually) |

**Weekly manual step:**
```bash
python manage.py review_submissions
python manage.py approve_submissions
python manage.py reject_submissions
```

**Cost:** ~50 Firecrawl credits/day

---

## Configuration

```python
FIRECRAWL_API_KEY = "fc-..."
OPENAI_API_KEY = "sk-..."
```
