FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY lovdata_pipeline/ lovdata_pipeline/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p /app/data/raw \
    /app/data/extracted \
    /app/data/chromadb \
    /app/dagster_home/storage \
    /app/dagster_home/logs \
    /app/dagster_home/artifacts

# Copy Dagster configuration
COPY dagster_home/dagster.yaml /app/dagster_home/

# Set environment variables
ENV DAGSTER_HOME=/app/dagster_home
ENV PYTHONUNBUFFERED=1

# Expose ports for Dagster webserver
EXPOSE 3000

# Run Dagster
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000", "-m", "lovdata_pipeline"]
