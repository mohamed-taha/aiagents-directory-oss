# Contributing

## Development Setup

```bash
git clone https://github.com/yourusername/aiagents-directory.git
cd aiagents-directory
python -m venv venv && source venv/bin/activate
pip install -r requirements/local.txt
npm install
cp .env.example .env
```

## Running

```bash
python manage.py migrate
python manage.py runserver

# Celery (separate terminal)
celery -A config.celery_app worker -l info
```

## Tests

```bash
pytest
```

## Code Style

The project has `black`, `isort`, and `djlint` configured but formatting isn't strictly enforced. This was a solo project focused on shipping fast. Feel free to run them if you'd like:

```bash
black aiagents_directory
isort aiagents_directory
djlint aiagents_directory/templates --reformat
```
