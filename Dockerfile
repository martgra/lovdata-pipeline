FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY lovdata_pipeline ./lovdata_pipeline

# Install the package
RUN uv pip install -e .

# Create data directory
RUN mkdir -p /data/raw /data/extracted /data/chunks /data/enriched

# Set working directory for data
WORKDIR /data

# Default command shows help
CMD ["uv", "run", "python", "-m", "lovdata_pipeline", "--help"]
