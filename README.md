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

The core innovation: a fully automated pipeline that discovers AI agents from the web.

```
                                    ┌─────────────────┐
                                    │  SERP Search    │
                                    │  (Firecrawl)    │
                                    └────────┬────────┘
                                             │
                                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              SOURCING                                         │
│  • Searches Google with curated queries ("AI sales agent", "AI coding agent")│
│  • Filters URLs (blocklists, allowlists, path patterns)                       │
│  • Deduplicates against existing agents                                       │
│  • Creates AgentSubmission records                                            │
└──────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              ENRICHMENT                                       │
│  • Scrapes agent website via Firecrawl/Zyte                                  │
│  • Extracts: name, description, features, use cases, pricing                 │
│  • Downloads logo and screenshot                                              │
│  • Handles aggregator pages (extracts real product URL)                       │
└──────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              AI REVIEW                                        │
│  • GPT-4 validates if URL is a legitimate AI agent                           │
│  • Detects: templates, feature pages, blog posts, academic papers            │
│  • Returns: decision (approved/rejected), confidence score, reasoning        │
│  • Auto-applies decisions above confidence threshold                          │
└──────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │  Published      │
                                    │  Agent          │
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
