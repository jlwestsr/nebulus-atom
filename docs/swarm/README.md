# Nebulus Swarm Operations Guide

Nebulus Swarm is an autonomous agent orchestration system with an Overlord + Minions architecture. The Overlord monitors Slack and GitHub for work, spawning ephemeral Minion containers to implement features and fix bugs.

## Architecture Overview

```
                    ┌─────────────┐
                    │   GitHub    │
                    │   Issues    │
                    └──────┬──────┘
                           │ nebulus-ready label
                    ┌──────▼──────┐
┌─────────┐        │   Overlord  │        ┌─────────────┐
│  Slack  │◄──────►│  (control   │◄──────►│  Local LLM  │
│ Channel │        │   plane)    │        │  (Nebulus)  │
└─────────┘        └──────┬──────┘        └─────────────┘
                          │
           ┌──────────────┼──────────────┐
           │              │              │
    ┌──────▼──────┐┌──────▼──────┐┌──────▼──────┐
    │   Minion    ││   Minion    ││   Minion    │
    │ (ephemeral) ││ (ephemeral) ││ (ephemeral) │
    └─────────────┘└─────────────┘└─────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- GitHub Personal Access Token with repo permissions
- Slack App with Socket Mode enabled
- Local LLM server (Nebulus/Ollama) running

### 1. Configure Environment

```bash
# Copy example config
cp .env.swarm.example .env.swarm

# Edit with your credentials
vim .env.swarm
```

Required environment variables:
- `SLACK_BOT_TOKEN` - Slack Bot OAuth Token (xoxb-...)
- `SLACK_APP_TOKEN` - Slack App-Level Token for Socket Mode (xapp-...)
- `SLACK_CHANNEL_ID` - Channel ID to monitor (C...)
- `GITHUB_TOKEN` - GitHub Personal Access Token (ghp_...)
- `GITHUB_WATCHED_REPOS` - Comma-separated repos (owner/repo1,owner/repo2)

### 2. Build Images

```bash
# Build Overlord image
docker build -t nebulus-overlord:latest -f nebulus_swarm/overlord/Dockerfile .

# Build Minion image
docker build -t nebulus-minion:latest -f nebulus_swarm/minion/Dockerfile .
```

### 3. Start Overlord

```bash
docker-compose -f docker-compose.swarm.yml up -d overlord
```

### 4. Verify

```bash
# Check health
curl http://localhost:8080/health

# Check detailed status
curl http://localhost:8080/status
```

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | Yes | - | Slack Bot OAuth Token |
| `SLACK_APP_TOKEN` | Yes | - | Slack App-Level Token |
| `SLACK_CHANNEL_ID` | Yes | - | Channel to monitor |
| `GITHUB_TOKEN` | Yes | - | GitHub PAT |
| `GITHUB_WATCHED_REPOS` | Yes | - | Comma-separated repos |
| `GITHUB_DEFAULT_REPO` | No | - | Default repo for commands |
| `NEBULUS_BASE_URL` | No | http://localhost:5000/v1 | LLM server URL |
| `NEBULUS_MODEL` | No | qwen3-coder-30b | Model name |
| `NEBULUS_TIMEOUT` | No | 600 | Request timeout (seconds) |
| `MAX_CONCURRENT_MINIONS` | No | 3 | Max parallel minions |
| `CRON_ENABLED` | No | true | Enable cron sweeps |
| `CRON_SCHEDULE` | No | 0 2 * * * | Cron schedule |
| `LOG_LEVEL` | No | INFO | Log level |
| `LOG_FORMAT` | No | console | json or console |
| `LOG_FILE` | No | - | Optional log file path |

### GitHub Labels

The Overlord uses these labels to track issue state:

| Label | Description |
|-------|-------------|
| `nebulus-ready` | Issue is ready for a Minion to work on |
| `in-progress` | Minion is actively working on it |
| `in-review` | PR created, awaiting review |
| `needs-attention` | Minion failed, needs human review |
| `high-priority` | Higher priority in queue |

## Slack Commands

Send these commands in the monitored Slack channel:

| Command | Description |
|---------|-------------|
| `status` | Show active minions and queue status |
| `queue` | Show pending issues from GitHub |
| `work on owner/repo#123` | Start work on specific issue |
| `work on #123` | Start work (uses default repo) |
| `stop #123` | Stop minion working on issue |
| `stop minion-abc123` | Stop specific minion |
| `pause` | Pause automatic queue processing |
| `resume` | Resume queue processing |
| `history` | Show recent work history |
| `help` | Show available commands |

## Troubleshooting

### Overlord won't start

1. Check Docker is running: `docker ps`
2. Verify environment: `docker-compose -f docker-compose.swarm.yml config`
3. Check logs: `docker logs overlord`

### Minion containers stuck

1. Check watchdog: Minions without heartbeat for 5 minutes are auto-killed
2. Manual stop: Send `stop minion-<id>` in Slack
3. Force cleanup: `docker rm -f $(docker ps -aq -f label=nebulus.swarm.minion)`

### Rate limit errors

1. Check quota: Send `queue` command to see remaining API calls
2. Wait for reset: The queue sweep skips when rate limited
3. Reduce watched repos to decrease API usage

### Minion fails immediately

1. Check LLM server is reachable from Docker network
2. Verify GitHub token has correct permissions
3. Check minion logs: `docker logs minion-<id>`

## Operational Runbook

### Daily Operations

- Check Slack channel for failed minion notifications
- Review PRs created by minions
- Monitor `#nebulus-swarm` channel for activity

### Maintenance Tasks

**Update images:**
```bash
docker-compose -f docker-compose.swarm.yml down
docker build -t nebulus-overlord:latest -f nebulus_swarm/overlord/Dockerfile .
docker build -t nebulus-minion:latest -f nebulus_swarm/minion/Dockerfile .
docker-compose -f docker-compose.swarm.yml up -d overlord
```

**View logs:**
```bash
# Overlord logs
docker logs -f overlord

# Specific minion logs
docker logs minion-<id>
```

**Clean up old containers:**
```bash
# Remove stopped minion containers
docker container prune -f --filter label=nebulus.swarm.minion
```

### Incident Response

**High failure rate:**
1. Pause queue: Send `pause` in Slack
2. Check LLM server health
3. Review recent failures for patterns
4. Resume when resolved: Send `resume`

**Overlord crash:**
1. Check Docker: `docker ps -a | grep overlord`
2. View logs: `docker logs overlord`
3. Restart: `docker-compose -f docker-compose.swarm.yml up -d overlord`
4. Overlord will resume with persisted state

### Backup and Recovery

**State database:**
```bash
# Backup
docker cp overlord:/var/lib/overlord/state.db ./state.db.backup

# Restore
docker cp ./state.db.backup overlord:/var/lib/overlord/state.db
docker restart overlord
```

## Monitoring

### Health Endpoint

```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "active_minions": 2,
  "paused": false,
  "docker_available": true
}
```

### Status Endpoint

```bash
curl http://localhost:8080/status
```

Returns detailed information about:
- Active minions with status
- Docker container states
- Configuration summary

### Log Analysis

For JSON logs (`LOG_FORMAT=json`):

```bash
# Count errors in last hour
docker logs overlord --since 1h 2>&1 | grep '"level":"ERROR"' | wc -l

# Find rate limit events
docker logs overlord 2>&1 | grep "rate_limited"

# Track specific minion
docker logs overlord 2>&1 | grep "minion-abc123"
```
