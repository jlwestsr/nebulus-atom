"""Configuration for Nebulus Swarm."""

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

# Load .env from current working directory
load_dotenv(os.path.join(os.getcwd(), ".env"))


@dataclass
class SlackConfig:
    """Slack integration configuration."""

    bot_token: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    app_token: str = field(default_factory=lambda: os.getenv("SLACK_APP_TOKEN", ""))
    channel_id: str = field(default_factory=lambda: os.getenv("SLACK_CHANNEL_ID", ""))


@dataclass
class GitHubConfig:
    """GitHub integration configuration."""

    token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    default_repo: str = field(
        default_factory=lambda: os.getenv("GITHUB_DEFAULT_REPO", "")
    )
    watched_repos: List[str] = field(default_factory=list)
    work_label: str = "nebulus-ready"
    in_progress_label: str = "in-progress"
    needs_attention_label: str = "needs-attention"


@dataclass
class MinionConfig:
    """Minion container configuration."""

    image: str = "nebulus-minion:latest"
    max_concurrent: int = 3
    timeout_minutes: int = 30
    network: str = "nebulus-swarm"


@dataclass
class LLMConfig:
    """LLM backend configuration for Minions."""

    base_url: str = field(
        default_factory=lambda: os.getenv(
            "NEBULUS_BASE_URL", "http://localhost:5000/v1"
        )
    )
    model: str = field(
        default_factory=lambda: os.getenv("NEBULUS_MODEL", "qwen3-coder-30b")
    )
    timeout: int = field(
        default_factory=lambda: int(os.getenv("NEBULUS_TIMEOUT", "600"))
    )
    streaming: bool = field(
        default_factory=lambda: os.getenv("NEBULUS_STREAMING", "false").lower()
        == "true"
    )


@dataclass
class CronConfig:
    """Cron scheduling configuration."""

    enabled: bool = True
    schedule: str = "0 2 * * *"  # Daily at 2 AM


@dataclass
class ReviewerConfig:
    """PR reviewer configuration."""

    enabled: bool = field(
        default_factory=lambda: os.getenv("REVIEWER_ENABLED", "true").lower() == "true"
    )
    auto_review: bool = field(
        default_factory=lambda: os.getenv("REVIEWER_AUTO_REVIEW", "true").lower()
        == "true"
    )
    auto_merge: bool = field(
        default_factory=lambda: os.getenv("REVIEWER_AUTO_MERGE", "false").lower()
        == "true"
    )
    merge_method: str = field(
        default_factory=lambda: os.getenv("REVIEWER_MERGE_METHOD", "squash")
    )
    min_confidence: float = field(
        default_factory=lambda: float(os.getenv("REVIEWER_MIN_CONFIDENCE", "0.8"))
    )


@dataclass
class OverlordLLMConfig:
    """LLM configuration for Overlord command parsing."""

    enabled: bool = field(
        default_factory=lambda: os.getenv("OVERLORD_LLM_ENABLED", "true").lower()
        == "true"
    )
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "OVERLORD_LLM_BASE_URL", "http://localhost:5000/v1"
        )
    )
    model: str = field(
        default_factory=lambda: os.getenv("OVERLORD_LLM_MODEL", "llama-3.1-8b")
    )
    timeout: float = field(
        default_factory=lambda: float(os.getenv("OVERLORD_LLM_TIMEOUT", "5.0"))
    )
    confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("OVERLORD_LLM_CONFIDENCE", "0.7"))
    )
    context_max_entries: int = field(
        default_factory=lambda: int(os.getenv("OVERLORD_LLM_CONTEXT_MAX", "10"))
    )
    context_ttl_minutes: int = field(
        default_factory=lambda: int(os.getenv("OVERLORD_LLM_CONTEXT_TTL", "30"))
    )


@dataclass
class SwarmConfig:
    """Main configuration for Nebulus Swarm."""

    slack: SlackConfig = field(default_factory=SlackConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    minions: MinionConfig = field(default_factory=MinionConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    cron: CronConfig = field(default_factory=CronConfig)
    reviewer: ReviewerConfig = field(default_factory=ReviewerConfig)
    overlord_llm: OverlordLLMConfig = field(default_factory=OverlordLLMConfig)

    # Overlord settings
    state_db_path: str = field(
        default_factory=lambda: os.getenv(
            "OVERLORD_STATE_DB", "/var/lib/overlord/state.db"
        )
    )
    health_port: int = field(
        default_factory=lambda: int(os.getenv("OVERLORD_HEALTH_PORT", "8080"))
    )
    heartbeat_timeout_seconds: int = 300  # 5 minutes

    @classmethod
    def from_env(cls) -> "SwarmConfig":
        """Create config from environment variables."""
        config = cls()

        # Parse watched repos from comma-separated env var
        repos_env = os.getenv("GITHUB_WATCHED_REPOS", "")
        if repos_env:
            config.github.watched_repos = [r.strip() for r in repos_env.split(",")]

        # Override max concurrent from env
        max_concurrent = os.getenv("MAX_CONCURRENT_MINIONS")
        if max_concurrent:
            config.minions.max_concurrent = int(max_concurrent)

        # Override cron schedule from env
        cron_schedule = os.getenv("CRON_SCHEDULE")
        if cron_schedule:
            config.cron.schedule = cron_schedule

        cron_enabled = os.getenv("CRON_ENABLED")
        if cron_enabled:
            config.cron.enabled = cron_enabled.lower() == "true"

        return config

    def validate(self) -> List[str]:
        """Validate configuration, return list of errors."""
        errors = []

        if not self.slack.bot_token:
            errors.append("SLACK_BOT_TOKEN is required")
        if not self.slack.app_token:
            errors.append("SLACK_APP_TOKEN is required (for Socket Mode)")
        if not self.slack.channel_id:
            errors.append("SLACK_CHANNEL_ID is required")
        if not self.github.token:
            errors.append("GITHUB_TOKEN is required")
        if not self.github.watched_repos:
            errors.append("GITHUB_WATCHED_REPOS is required (comma-separated)")

        return errors
