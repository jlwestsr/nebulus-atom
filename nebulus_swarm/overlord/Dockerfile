# Nebulus Swarm Overlord Container
# Always-on control plane that manages Minions

FROM python:3.12-slim

LABEL maintainer="West AI Labs"
LABEL description="Nebulus Swarm Overlord - Minion control plane"
LABEL org.opencontainers.image.source="https://github.com/jlwestsr/nebulus-atom"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the swarm package
COPY nebulus_swarm/ /app/nebulus_swarm/

# Create state directory
RUN mkdir -p /var/lib/overlord

# Set Python path
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED="1"

# Default configuration
ENV OVERLORD_STATE_DB="/var/lib/overlord/state.db"
ENV OVERLORD_HEALTH_PORT="8080"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${OVERLORD_HEALTH_PORT}/health || exit 1

# Expose health port
EXPOSE 8080

# Run Overlord
ENTRYPOINT ["python", "-m", "nebulus_swarm.overlord.main"]
