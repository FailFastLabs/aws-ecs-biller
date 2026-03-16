# CLAUDE.md

## Project Overview

Django REST Framework app for AWS cost analysis. Ingests AWS Cost & Usage Reports (CUR) from S3, processes them via ETL, and exposes analytics via REST API. Uses Celery for async ingestion jobs.

## Key Commands

```bash
# Install deps
pip install -r requirements/development.txt

# Run dev server
python manage.py runserver

# Run Celery worker
celery -A workers worker --loglevel=info

# Run tests
pytest

# Lint
ruff check .
ruff check --fix .

# Migrations
python manage.py makemigrations
python manage.py migrate

# Seed data
python manage.py load_fixture_cur
python manage.py load_pricing_fixtures
python manage.py seed_reservations
```

## Project Structure

```
apps/               # Django apps (accounts, ingestion, etl, costs, reservations,
│                   #   forecasting, anomalies, splitting, visualizations)
config/
├── settings/
│   ├── base.py         # shared settings
│   ├── development.py  # DEBUG=True, dev secret key
│   ├── test.py         # SQLite in-memory, eager Celery
│   └── production.py   # production (set via DJANGO_SETTINGS_MODULE)
├── urls.py             # all API routes under /api/v1/
workers/
└── celery.py           # Celery app config
tests/
├── unit/               # per-app unit tests
├── integration/        # API and pipeline integration tests
├── factories/          # Factory Boy model factories
└── fixtures/           # static CSV test data
requirements/
├── base.txt            # production deps
└── development.txt     # + pytest, ruff, moto, factory-boy
docker/
├── Dockerfile
└── docker-compose.yml
plans/                  # 10-part development spec (PART_0 through PART_9)
```

## Architecture Notes

- **Data flow**: S3 → ingestion app (Celery) → raw files in `cur_data/` → ETL app → `LineItem` rows in PostgreSQL
- **Settings**: `DJANGO_SETTINGS_MODULE` controls environment. Tests always use `config.settings.test`.
- **Celery**: Tasks auto-discovered from all installed apps. Broker and result backend both use Redis.
- **CUR storage**: Raw CUR files stored in `cur_data/` directory (auto-created on startup).
- **Forecasting**: Uses Chronos T5 model — heavy dependency, keep out of hot paths.
- **Anomaly detection**: Ensemble of z-score and Chronos sigma methods.
- **Cost splitting**: Allocation rules stored in DB; strategies are equal, proportional, or custom weights.

## Testing Conventions

- Test settings: `config.settings.test` (SQLite in-memory, `CELERY_TASK_ALWAYS_EAGER=True`)
- AWS calls mocked with `moto[s3]`
- Model factories in `tests/factories/` — prefer these over raw `Model.objects.create()`
- Coverage minimum: 80% on `apps/`; excludes migrations, fixtures, `manage.py`
- Integration tests hit a real PostgreSQL (spun up in CI via Docker service)

## Lint / Code Style

- Tool: `ruff` (replaces flake8, isort, pyupgrade, black)
- Line length: 100 (E501 ignored)
- Rules: E, F, I, UP, B, SIM
- Run `ruff check --fix .` to auto-fix imports and formatting

## CI/CD

- `.github/workflows/ci.yml` runs `ruff check .` then `pytest` on every push/PR
- `main` branch is protected: CI must pass + 1 review required
- CI services: PostgreSQL 16 on 5432, Redis 7 on 6379

## Environment Variables

| Variable | Notes |
|----------|-------|
| `DJANGO_SECRET_KEY` | Required in production |
| `DATABASE_URL` | PostgreSQL DSN; falls back to SQLite if unset |
| `REDIS_URL` | Celery broker/backend; defaults to `redis://localhost:6379/0` |
| `AWS_DEFAULT_REGION` | boto3 region |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | For S3 CUR downloads |

## Common Gotchas

- Migrations are excluded from coverage — don't add logic to migration files.
- `cur_data/` is gitignored — never commit raw CUR CSVs.
- The `forecasting` app loads a large ML model; avoid importing it in tests unless necessary.
- `config.settings.test` uses MD5 password hashing for speed — don't use in production.
