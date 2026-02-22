# AiAgents.Directory

A curated directory of AI agents with an automated discovery and review pipeline.

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Black code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Curated AI Agent Directory** - Browse and search AI agents by category, use case, and features
- **Automated Discovery Pipeline** - Discovers, enriches, and reviews AI agents automatically
- **Wagtail CMS Blog** - Built-in blog for content marketing
- **User Submissions** - Accept and review community-submitted agents

## Auto-Discovery Pipeline

How it works under the hood: a fully automated pipeline that discovers AI agents from the web.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              1. SOURCING                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Firecrawl Search API                                                     │   │
│  │ • Searches Google with rotating queries (evergreen + trending + category)│   │
│  │ • Returns blog posts, directories, list articles mentioning AI agents   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ LLM-Powered Extraction (via Firecrawl)                                  │   │
│  │ • JSON schema + prompt extracts AI agent products from each page        │   │
│  │ • Finds agents buried in list articles, not just homepage links         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ URL Filtering Pipeline                                                   │   │
│  │ • Domain blocklist → Aggregator detection → Path filtering → Allowlist  │   │
│  │ • Deduplicates against existing agents                                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              2. ENRICHMENT                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Firecrawl Scrape (single API call, multiple formats)                    │   │
│  │ • JSON: Schema-guided extraction (features, pricing, use cases, etc.)   │   │
│  │ • Markdown: Raw content for AI review context                           │   │
│  │ • Screenshot: Viewport capture (auto-downloaded before expiry)          │   │
│  │ • Branding: Logo, colors, fonts                                         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Aggregator Handling                                                      │   │
│  │ • Detects ProductHunt/YC/Crunchbase pages                               │   │
│  │ • Extracts actual product URL via secondary LLM extraction              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              3. AI REVIEW                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Pydantic AI Agent (GPT-powered)                                         │   │
│  │ • Validates if submission is a legitimate AI agent                      │   │
│  │ • Input: name, URL, enrichment data, raw markdown                       │   │
│  │ • Output: Structured ReviewResult (Pydantic model)                      │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Classification & Flags                                                   │   │
│  │ • Detects: template pages, feature subpages, aggregator listings,       │   │
│  │   blog posts, academic papers, prohibited content                        │   │
│  │ • Returns: decision + confidence score (0-1) + reasoning + flags        │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Confidence-Based Auto-Apply                                              │   │
│  │ • confidence ≥ 0.7 → auto-approve/reject                                │   │
│  │ • confidence < 0.7 → flag for manual review                             │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   Published     │
                              │     Agent       │
                              └─────────────────┘
```

### Pipeline Commands

```bash
# Full pipeline
python manage.py source_agents --limit 50 --auto-enrich
python manage.py review_submissions --auto-apply
python manage.py approve_submissions

# Or run daily via Celery Beat (6:00 AM UTC)
```

## Quick Start

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements/local.txt && npm install
cp .env.example .env  # Add your API keys

# Run
python manage.py migrate
python manage.py runserver

# Celery (separate terminal)
celery -A config.celery_app worker -l info
```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | AI review | Yes* |
| `FIRECRAWL_API_KEY` | Scraping/SERP | Yes* |
| `CELERY_BROKER_URL` | Redis URL | Yes |

*Required for auto-discovery

## Tech Stack

Django 4.2 / Celery / Tailwind CSS / Wagtail CMS / OpenAI / Firecrawl

## License

MIT - see [LICENSE](LICENSE)
