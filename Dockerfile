FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml .
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY prompts/ prompts/
COPY main.py .

# Install python dependencies
RUN pip install --no-cache-dir .

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
