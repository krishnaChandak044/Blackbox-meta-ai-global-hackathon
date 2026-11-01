FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libglib2.0-0 libcairo2 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY services ./services
COPY engine ./engine
RUN pip install --no-cache-dir .
COPY contracts ./contracts
CMD ["celery", "-A", "services.worker.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
