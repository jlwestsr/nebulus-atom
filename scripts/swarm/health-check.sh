#!/usr/bin/env bash
# Health check script for Nebulus Swarm Overlord
#
# Usage:
#   ./scripts/swarm/health-check.sh              # Check localhost:8080
#   ./scripts/swarm/health-check.sh hostname:port # Check custom endpoint
#
# Exit codes:
#   0 - Healthy
#   1 - Unhealthy or unreachable

set -euo pipefail

# Default endpoint
ENDPOINT="${1:-localhost:8080}"
TIMEOUT="${TIMEOUT:-5}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_health() {
    local response
    local http_code

    # Make request and capture both body and status code
    response=$(curl -s -w "\n%{http_code}" \
        --max-time "$TIMEOUT" \
        "http://$ENDPOINT/health" 2>/dev/null) || {
        echo -e "${RED}UNHEALTHY${NC}: Cannot reach Overlord at $ENDPOINT"
        return 1
    }

    # Split response into body and status code
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [[ "$http_code" != "200" ]]; then
        echo -e "${RED}UNHEALTHY${NC}: HTTP $http_code"
        return 1
    fi

    # Parse JSON response
    status=$(echo "$body" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    active_minions=$(echo "$body" | grep -o '"active_minions":[0-9]*' | cut -d':' -f2)
    paused=$(echo "$body" | grep -o '"paused":[a-z]*' | cut -d':' -f2)
    docker_available=$(echo "$body" | grep -o '"docker_available":[a-z]*' | cut -d':' -f2)

    if [[ "$status" != "healthy" ]]; then
        echo -e "${RED}UNHEALTHY${NC}: Status is $status"
        return 1
    fi

    # Build status message
    echo -e "${GREEN}HEALTHY${NC}"
    echo "  Active minions: $active_minions"
    echo "  Queue paused: $paused"
    echo "  Docker available: $docker_available"

    # Warn if Docker is unavailable
    if [[ "$docker_available" == "false" ]]; then
        echo -e "  ${YELLOW}WARNING${NC}: Docker is not available"
    fi

    return 0
}

# Get detailed status
get_status() {
    echo "Fetching detailed status..."
    curl -s "http://$ENDPOINT/status" | python3 -m json.tool 2>/dev/null || {
        echo "Failed to get detailed status"
        return 1
    }
}

# Main
case "${2:-health}" in
    health)
        check_health
        ;;
    status)
        get_status
        ;;
    *)
        echo "Usage: $0 [endpoint] [health|status]"
        exit 1
        ;;
esac
