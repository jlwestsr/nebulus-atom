#!/usr/bin/env bash
# Deploy Nebulus Swarm to a server
#
# Usage:
#   ./scripts/swarm/deploy.sh              # Deploy locally
#   ./scripts/swarm/deploy.sh user@host    # Deploy to remote server
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - .env.swarm file configured
#   - SSH access (for remote deployment)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    log_step "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi

    if [[ ! -f "$PROJECT_ROOT/.env.swarm" ]]; then
        log_error ".env.swarm not found. Copy from .env.swarm.example and configure."
        exit 1
    fi

    log_info "Prerequisites OK"
}

# Build images
build_images() {
    log_step "Building Docker images..."
    "$SCRIPT_DIR/build.sh" all
}

# Deploy locally
deploy_local() {
    log_step "Deploying locally..."

    cd "$PROJECT_ROOT"

    # Stop existing containers
    log_info "Stopping existing containers..."
    docker-compose -f docker-compose.swarm.yml down 2>/dev/null || true

    # Start Overlord
    log_info "Starting Overlord..."
    docker-compose -f docker-compose.swarm.yml up -d overlord

    # Wait for health
    log_info "Waiting for Overlord to be healthy..."
    for i in {1..30}; do
        if curl -s http://localhost:8080/health > /dev/null 2>&1; then
            log_info "Overlord is healthy!"
            return 0
        fi
        sleep 1
    done

    log_error "Overlord failed to become healthy"
    docker logs overlord --tail 50
    exit 1
}

# Deploy to remote server
deploy_remote() {
    local target="$1"
    log_step "Deploying to $target..."

    # Create remote directory
    log_info "Creating remote directory..."
    ssh "$target" "mkdir -p /opt/nebulus-atom"

    # Sync files
    log_info "Syncing project files..."
    rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude '.nebulus_atom' --exclude 'venv' --exclude '.venv' \
        "$PROJECT_ROOT/" "$target:/opt/nebulus-atom/"

    # Copy env file
    log_info "Copying environment file..."
    scp "$PROJECT_ROOT/.env.swarm" "$target:/opt/nebulus-atom/.env.swarm"

    # Build and deploy on remote
    log_info "Building images on remote..."
    ssh "$target" "cd /opt/nebulus-atom && ./scripts/swarm/build.sh all"

    log_info "Starting Overlord on remote..."
    ssh "$target" "cd /opt/nebulus-atom && docker-compose -f docker-compose.swarm.yml up -d overlord"

    # Check health
    log_info "Checking remote health..."
    sleep 5
    if ssh "$target" "curl -s http://localhost:8080/health" | grep -q "healthy"; then
        log_info "Remote deployment successful!"
    else
        log_warn "Remote health check inconclusive, please verify manually"
    fi
}

# Install systemd service
install_service() {
    log_step "Installing systemd service..."

    if [[ ! -f /etc/systemd/system/nebulus-overlord.service ]]; then
        sudo cp "$SCRIPT_DIR/nebulus-overlord.service" /etc/systemd/system/
        sudo systemctl daemon-reload
        log_info "Service file installed"
    else
        log_info "Service file already exists"
    fi

    # Create env directory
    sudo mkdir -p /etc/nebulus-swarm

    # Copy env file
    if [[ -f "$PROJECT_ROOT/.env.swarm" ]]; then
        sudo cp "$PROJECT_ROOT/.env.swarm" /etc/nebulus-swarm/overlord.env
        sudo chmod 600 /etc/nebulus-swarm/overlord.env
        log_info "Environment file installed"
    fi

    log_info "Enable and start with: sudo systemctl enable --now nebulus-overlord"
}

# Main
main() {
    local target="${1:-local}"

    echo "========================================"
    echo "  Nebulus Swarm Deployment"
    echo "========================================"
    echo

    check_prerequisites

    case "$target" in
        local)
            build_images
            deploy_local
            ;;
        install-service)
            install_service
            ;;
        *@*)
            build_images
            deploy_remote "$target"
            ;;
        *)
            log_error "Unknown target: $target"
            echo "Usage: $0 [local|user@host|install-service]"
            exit 1
            ;;
    esac

    echo
    log_info "Deployment complete!"
    echo
    echo "Next steps:"
    echo "  - Check status: curl http://localhost:8080/status"
    echo "  - View logs: docker logs -f overlord"
    echo "  - Send 'help' in Slack to see commands"
}

main "$@"
