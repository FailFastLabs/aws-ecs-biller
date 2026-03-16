ARG TARGETPLATFORM
FROM --platform=${TARGETPLATFORM:-linux/amd64} python:3.11-slim AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/base.txt
RUN uv pip install -r requirements/base.txt --system

COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings.production

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
