# Nebulus Swarm Minion Container
# Ephemeral worker that implements GitHub issues autonomously

FROM python:3.12-slim

LABEL maintainer="West AI Labs"
LABEL description="Nebulus Swarm Minion - autonomous GitHub worker"
LABEL org.opencontainers.image.source="https://github.com/jlwestsr/nebulus-atom"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Create workspace directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements-minion.txt .
RUN pip install --no-cache-dir -r requirements-minion.txt

# Copy the swarm package
COPY nebulus_swarm/ /app/nebulus_swarm/
COPY nebulus_atom/ /app/nebulus_atom/

# Create workspace for cloned repos
RUN mkdir -p /workspace

# Environment variables (overridden at runtime)
ENV MINION_ID=""
ENV GITHUB_REPO=""
ENV GITHUB_ISSUE=""
ENV GITHUB_TOKEN=""
ENV OVERLORD_CALLBACK_URL="http://overlord:8080/minion/report"
ENV NEBULUS_BASE_URL="http://localhost:5000/v1"
ENV NEBULUS_MODEL="qwen3-coder-30b"
ENV NEBULUS_TIMEOUT="600"
ENV NEBULUS_STREAMING="false"

# Set Python path
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED="1"

# Health check - minion reports to overlord, not external
HEALTHCHECK NONE

# Default timeout (30 minutes)
ENV MINION_TIMEOUT="1800"

# Entrypoint
ENTRYPOINT ["python", "-m", "nebulus_swarm.minion.main"]
