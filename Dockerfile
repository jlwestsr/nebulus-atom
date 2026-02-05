# Build Stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Final Stage
FROM python:3.12-slim

WORKDIR /app

# Create a non-root user
RUN groupadd -r nebulus && useradd -r -g nebulus nebulus

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir /wheels/*

# Copy application code
COPY . .

# Set ownership to non-root user
RUN chown -R nebulus:nebulus /app

# Ensure home directory exists and is writable
RUN mkdir -p /home/nebulus && chown -R nebulus:nebulus /home/nebulus

# Switch to non-root user
USER nebulus

# Define environment variable
ENV PYTHONUNBUFFERED=1
ENV PATH="/home/nebulus/.local/bin:${PATH}"

# Default command
CMD ["/bin/bash"]
