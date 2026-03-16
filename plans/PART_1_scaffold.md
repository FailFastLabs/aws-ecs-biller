# PART 1 — Project Scaffold

## Objective
Initialize the Django project, git repo, GitHub repo, docker-compose, and CI pipeline.
Everything needed so Parts 2–9 can just add apps.

## Working Directory
`/Users/mfeldman/Documents/python/aws_ecs_biller`

---

## Steps

### 1. Create Python virtual environment + install Django
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install django==5.1.* djangorestframework==3.15.* psycopg[binary]==3.* celery[redis]==5.4.* redis==5.* django-filter==24.*
django-admin startproject config .
```

### 2. Create app directories
```bash
mkdir -p apps/{accounts,ingestion,etl,costs,reservations,forecasting,anomalies,splitting,visualizations}
mkdir -p workers tests/{unit,integration,fixtures,factories} scripts/management/commands docker
touch apps/__init__.py
# touch __init__.py in each app dir
```

### 3. Settings split

Create `config/settings/` with:

**`base.py`** — shared:
```python
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = False
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'apps.accounts',
    'apps.ingestion',
    'apps.etl',
    'apps.costs',
    'apps.reservations',
    'apps.forecasting',
    'apps.anomalies',
    'apps.splitting',
    'apps.visualizations',
]

DATABASES = {
    'default': dj_database_url.config(default=os.environ['DATABASE_URL'])
}

CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
}

CUR_LOCAL_STORAGE = BASE_DIR / 'cur_data'
CUR_LOCAL_STORAGE.mkdir(exist_ok=True)
```

**`development.py`**:
```python
from .base import *
DEBUG = True
SECRET_KEY = 'dev-secret-key-not-for-production'
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', ...}}
```

**`test.py`**:
```python
from .base import *
DEBUG = True
SECRET_KEY = 'test-secret-key'
DATABASES = {'default': dj_database_url.config(default='postgresql://test:test@localhost/test_cur')}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

**`production.py`**: Use env vars for everything, no hardcoded values.

### 4. `config/urls.py`
```python
from django.urls import path, include
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('apps.costs.urls')),
    path('api/v1/', include('apps.reservations.urls')),
    path('api/v1/', include('apps.forecasting.urls')),
    path('api/v1/', include('apps.anomalies.urls')),
    path('api/v1/', include('apps.splitting.urls')),
    path('api/v1/viz/', include('apps.visualizations.urls')),
    path('api/v1/', include('apps.ingestion.urls')),
    path('api/v1/', include('apps.accounts.urls')),
]
```

### 5. `workers/celery.py`
```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
app = Celery('aws_ecs_biller')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

### 6. `requirements/base.txt`
```
Django==5.1.*
djangorestframework==3.15.*
django-filter==24.*
dj-database-url==2.*
celery[redis]==5.4.*
redis==5.*
psycopg[binary]==3.*
boto3==1.35.*
pandas==2.2.*
pyarrow==17.*
chronos-forecasting==1.*
pulp==2.8.*
scikit-learn==1.5.*
numpy==1.26.*
plotly==5.24.*
```

`requirements/development.txt`:
```
-r base.txt
factory-boy==3.3.*
pytest-django==4.8.*
pytest-cov==5.*
moto[s3]==5.*
ruff==0.6.*
mypy==1.11.*
django-stubs==5.*
```

### 7. `pyproject.toml`
```toml
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E","F","I","UP","B","SIM"]

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
plugins = ["mypy_django_plugin.main"]

[tool.django-stubs]
django_settings_module = "config.settings.test"

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.test"
python_files = ["test_*.py"]
addopts = "--cov=apps --cov-report=term-missing --cov-fail-under=80"

[tool.coverage.run]
omit = ["*/migrations/*","*/tests/*","manage.py"]
```

### 8. `.gitignore`
```
__pycache__/
*.py[cod]
.venv/
venv/
dist/
*.egg-info/
.env
*.env
aws_credentials*
*secret*
*.pem
*.key
db.sqlite3
/staticfiles/
/media/
/cur_data/
*.parquet
*.snappy
.coverage
htmlcov/
.pytest_cache/
.DS_Store
.idea/
.vscode/
```

### 9. `.env.example`
```
DJANGO_SECRET_KEY=change-me
DATABASE_URL=postgresql://cur_user:password@localhost:5432/aws_cur
REDIS_URL=redis://localhost:6379/0
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

### 10. `docker/docker-compose.yml`
```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: aws_cur
      POSTGRES_USER: cur_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devpassword}
    volumes: [pgdata:/var/lib/postgresql/data]
    ports: ["5432:5432"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  web:
    build: {context: .., dockerfile: docker/Dockerfile}
    command: python manage.py runserver 0.0.0.0:8000
    volumes: [..:/app]
    env_file: ../.env
    ports: ["8000:8000"]
    depends_on: [db, redis]
  celery-worker:
    build: {context: .., dockerfile: docker/Dockerfile}
    command: celery -A workers worker --loglevel=info
    volumes: [..:/app]
    env_file: ../.env
    depends_on: [db, redis]
volumes:
  pgdata:
```

`docker/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt
COPY . .
ENV DJANGO_SETTINGS_MODULE=config.settings.production
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

### 11. `.github/workflows/ci.yml`
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: {POSTGRES_DB: test_cur, POSTGRES_USER: test, POSTGRES_PASSWORD: test}
        options: --health-cmd pg_isready --health-interval 10s --health-retries 5
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11', cache: pip}
      - run: pip install -r requirements/development.txt
      - run: ruff check .
      - run: pytest
        env:
          DATABASE_URL: postgresql://test:test@localhost/test_cur
          REDIS_URL: redis://localhost:6379/0
          DJANGO_SECRET_KEY: ci-secret-key
          DJANGO_SETTINGS_MODULE: config.settings.test
```

### 12. Git + GitHub setup
```bash
git init
git branch -M main
git add .gitignore pyproject.toml requirements/ config/ workers/ docker/ manage.py .env.example
git commit -m "Initial project scaffold"

# Create GitHub repo (requires gh CLI authenticated)
gh repo create aws_ecs_biller --private --source=. --remote=origin --push

# Protect main branch
gh api repos/{owner}/aws_ecs_biller/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["test"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1}'
```

---

## Verification
```bash
python manage.py check --settings=config.settings.development
docker-compose -f docker/docker-compose.yml up -d db redis
python manage.py migrate --settings=config.settings.development
python manage.py runserver --settings=config.settings.development
# GET http://localhost:8000/admin/ → Django admin login page
```

---

## NEXT

After completing Part 1, run:
**`/Users/mfeldman/.claude/plans/PART_2_etl.md`**
