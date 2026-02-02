#!/usr/bin/env bash
# Build Nebulus Swarm Docker images
#
# Usage:
#   ./scripts/swarm/build.sh           # Build both images
#   ./scripts/swarm/build.sh overlord  # Build only Overlord
#   ./scripts/swarm/build.sh minion    # Build only Minion

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default tag
TAG="${TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

build_overlord() {
    log_info "Building Overlord image (nebulus-overlord:$TAG)..."
    docker build \
        -t "nebulus-overlord:$TAG" \
        -f "$PROJECT_ROOT/nebulus_swarm/overlord/Dockerfile" \
        "$PROJECT_ROOT"
    log_info "Overlord image built successfully"
}

build_minion() {
    log_info "Building Minion image (nebulus-minion:$TAG)..."
    docker build \
        -t "nebulus-minion:$TAG" \
        -f "$PROJECT_ROOT/nebulus_swarm/minion/Dockerfile" \
        "$PROJECT_ROOT"
    log_info "Minion image built successfully"
}

# Parse arguments
TARGET="${1:-all}"

case "$TARGET" in
    overlord)
        build_overlord
        ;;
    minion)
        build_minion
        ;;
    all)
        build_overlord
        build_minion
        log_info "All images built successfully"
        ;;
    *)
        log_error "Unknown target: $TARGET"
        echo "Usage: $0 [overlord|minion|all]"
        exit 1
        ;;
esac

# Show built images
log_info "Built images:"
docker images | grep -E "nebulus-(overlord|minion)" | head -5
