# AWS ECS Biller

A Django-based cost analysis and optimization platform for AWS infrastructure. Ingests AWS Cost & Usage Reports (CUR), analyzes spend, forecasts costs, detects anomalies, and generates reserved instance recommendations.

## What It Does

| App | Purpose |
|-----|---------|
| **accounts** | Manages AWS accounts and CUR manifest tracking |
| **ingestion** | Downloads CUR files from S3 via Celery tasks |
| **etl** | Deduplicates, normalizes, and loads CUR line items into the DB |
| **costs** | Core cost analytics — daily/hourly aggregates, pricing, tag filtering |
| **reservations** | RI/Savings Plan management and ROI-based purchase recommendations |
| **forecasting** | Time-series forecasting using Chronos T5 with confidence intervals |
| **anomalies** | Ensemble anomaly detection (z-score + Chronos sigma) with acknowledgment |
| **splitting** | Cost allocation across teams using equal/proportional/custom weight rules |
| **visualizations** | Plotly-based cost charts served via REST API |

## Requirements

- Python 3.11
- PostgreSQL 16
- Redis 7

## Quick Start (Docker)

```bash
cp .env.example .env
# Fill in required values (see Environment Variables below)

docker-compose -f docker/docker-compose.yml up
docker-compose -f docker/docker-compose.yml exec web python manage.py migrate
docker-compose -f docker/docker-compose.yml exec web python manage.py load_fixture_cur
```

App runs at http://localhost:8000

## Local Development

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt

cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py load_fixture_cur
python manage.py runserver

# In a separate terminal
celery -A workers worker --loglevel=info
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | Yes | Django secret key |
| `DATABASE_URL` | No | PostgreSQL URL (defaults to SQLite) |
| `REDIS_URL` | No | Redis URL (defaults to `redis://localhost:6379/0`) |
| `AWS_DEFAULT_REGION` | No | AWS region for boto3 |
| `AWS_ACCESS_KEY_ID` | No | AWS credentials for S3 CUR downloads |
| `AWS_SECRET_ACCESS_KEY` | No | AWS credentials for S3 CUR downloads |

## Testing

```bash
pytest                          # run all tests with coverage
pytest tests/unit/ -v           # unit tests only
pytest tests/integration/ -v    # integration tests only
```

Coverage minimum: **80%**. Tests use in-memory SQLite and synchronous Celery.

## Linting

```bash
ruff check .          # lint
ruff check --fix .    # lint + auto-fix
```

## API Endpoints

All endpoints are under `/api/v1/`:

- `/costs` — cost data and aggregates
- `/reservations` — RI and savings plan data
- `/forecasting` — cost forecasts
- `/anomalies` — detected anomalies
- `/splitting` — cost allocation
- `/viz/` — chart data
- `/ingestion` — CUR ingestion jobs
- `/accounts` — AWS account management

## CI/CD

GitHub Actions runs on every push and PR:
1. `ruff check .` — lint
2. `pytest` — tests with 80% coverage gate

PRs to `main` require passing CI and one approving review.

## Fixture / Seed Data

```bash
python manage.py load_fixture_cur       # load sample CUR data
python manage.py load_pricing_fixtures  # load EC2 pricing data
python manage.py seed_reservations      # create mock RI/savings plan records
```
