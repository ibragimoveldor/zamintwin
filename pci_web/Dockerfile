FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev gcc ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic needs settings but .env doesn't exist during build.
# Use production settings and provide minimal env vars for the build step only.
ENV DJANGO_SETTINGS_MODULE=config.settings.production
ENV SECRET_KEY=build-only-dummy-key
ENV DATABASE_URL=sqlite:///tmp/build.db
RUN python manage.py collectstatic --noinput || true

# Clear build-only env vars (runtime values come from docker-compose)
ENV SECRET_KEY=""
ENV DATABASE_URL=""
ENV DJANGO_SETTINGS_MODULE=config.settings.development

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "600"]
