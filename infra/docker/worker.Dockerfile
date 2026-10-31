FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY services ./services
COPY engine ./engine
RUN pip install --no-cache-dir .
COPY contracts ./contracts
CMD ["celery", "-A", "services.worker.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
