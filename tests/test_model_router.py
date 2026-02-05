"""Tests for Multi-LLM model routing."""

import json
import sys
from unittest.mock import MagicMock, patch


# Mock slack_bolt before importing Overlord modules
sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("slack_bolt.adapter", MagicMock())
sys.modules.setdefault("slack_bolt.adapter.socket_mode", MagicMock())
sys.modules.setdefault("slack_bolt.adapter.socket_mode.async_handler", MagicMock())
sys.modules.setdefault("slack_bolt.async_app", MagicMock())


# ---------------------------------------------------------------------------
# ModelProfile and RoutingConfig
# ---------------------------------------------------------------------------


class TestModelProfile:
    """Tests for ModelProfile dataclass."""

    def test_model_profile_creation(self):
        from nebulus_swarm.config import ModelProfile

        profile = ModelProfile(
            name="llama-3.1-8b",
            tier="light",
            base_url="http://localhost:5000/v1",
            timeout=300,
        )
        assert profile.name == "llama-3.1-8b"
        assert profile.tier == "light"
        assert profile.timeout == 300

    def test_model_profile_to_llm_config(self):
        from nebulus_swarm.config import ModelProfile

        profile = ModelProfile(
            name="qwen3-coder-30b",
            tier="heavy",
            base_url="http://gpu-server:8080/v1",
            timeout=600,
            streaming=True,
        )
        llm_config = profile.to_llm_config()
        assert llm_config.model == "qwen3-coder-30b"
        assert llm_config.base_url == "http://gpu-server:8080/v1"
        assert llm_config.timeout == 600
        assert llm_config.streaming is True

    def test_model_profile_defaults(self):
        from nebulus_swarm.config import ModelProfile

        profile = ModelProfile(name="test-model", tier="light")
        assert profile.base_url == ""
        assert profile.timeout == 600
        assert profile.streaming is False


class TestRoutingConfig:
    """Tests for RoutingConfig dataclass."""

    def test_routing_config_defaults(self):
        from nebulus_swarm.config import RoutingConfig

        config = RoutingConfig()
        assert config.enabled is False
        assert config.complexity_threshold == 5
        assert config.default_tier == "heavy"
        assert config.models == {}

    def test_routing_config_get_model(self):
        from nebulus_swarm.config import ModelProfile, RoutingConfig

        config = RoutingConfig(
            models={
                "light": ModelProfile(name="small-model", tier="light"),
                "heavy": ModelProfile(name="big-model", tier="heavy"),
            }
        )
        assert config.get_model("light").name == "small-model"
        assert config.get_model("heavy").name == "big-model"
        assert config.get_model("unknown") is None

    @patch.dict(
        "os.environ",
        {
            "ROUTING_ENABLED": "true",
            "ROUTING_COMPLEXITY_THRESHOLD": "3",
            "ROUTING_DEFAULT_TIER": "light",
            "ROUTING_MODELS": json.dumps(
                {
                    "light": {"name": "llama-8b", "base_url": "http://a:5000/v1"},
                    "heavy": {"name": "qwen-30b", "base_url": "http://b:8080/v1"},
                }
            ),
        },
    )
    def test_routing_config_from_env(self):
        from nebulus_swarm.config import RoutingConfig

        config = RoutingConfig.from_env()
        assert config.models["light"].name == "llama-8b"
        assert config.models["heavy"].name == "qwen-30b"
        assert config.models["light"].base_url == "http://a:5000/v1"

    @patch.dict("os.environ", {"ROUTING_MODELS": "invalid json"})
    def test_routing_config_from_env_bad_json(self):
        from nebulus_swarm.config import RoutingConfig

        config = RoutingConfig.from_env()
        assert config.models == {}


# ---------------------------------------------------------------------------
# ModelRouter: Complexity Analysis
# ---------------------------------------------------------------------------


class TestComplexityAnalysis:
    """Tests for ModelRouter.analyze_complexity."""

    def _make_router(self, threshold=5):
        from nebulus_swarm.config import RoutingConfig
        from nebulus_swarm.overlord.model_router import ModelRouter

        config = RoutingConfig(enabled=True, complexity_threshold=threshold)
        return ModelRouter(config)

    def test_empty_issue_scores_zero(self):
        router = self._make_router()
        result = router.analyze_complexity("", "", [])
        assert result.score == 0
        assert result.tier == "light"

    def test_simple_labels_reduce_score(self):
        router = self._make_router()
        result = router.analyze_complexity("Fix stuff", "", ["docs", "typo"])
        assert result.score == 0  # Clamped from -2
        assert result.tier == "light"
        assert any("simple labels" in r for r in result.reasons)

    def test_complex_labels_increase_score(self):
        router = self._make_router()
        result = router.analyze_complexity(
            "Refactor auth", "", ["refactor", "security"]
        )
        assert result.score >= 2
        assert any("complex labels" in r for r in result.reasons)

    def test_long_body_increases_score(self):
        router = self._make_router()
        long_body = "x" * 2500
        result = router.analyze_complexity("Task", long_body, [])
        assert result.score >= 2
        assert any("long body" in r for r in result.reasons)

    def test_medium_body_increases_score(self):
        router = self._make_router()
        medium_body = "x" * 1000
        result = router.analyze_complexity("Task", medium_body, [])
        assert result.score >= 1
        assert any("medium body" in r for r in result.reasons)

    def test_checklist_items_increase_score(self):
        router = self._make_router()
        body = "\n".join([f"- [{'x' if i % 2 else ' '}] Task {i}" for i in range(6)])
        result = router.analyze_complexity("Task", body, [])
        assert result.score >= 2
        assert any("checklist" in r for r in result.reasons)

    def test_code_blocks_increase_score(self):
        router = self._make_router()
        body = "```python\ncode\n```\n```js\ncode\n```\n```css\ncode\n```"
        result = router.analyze_complexity("Task", body, [])
        assert result.score >= 1
        assert any("code blocks" in r for r in result.reasons)

    def test_file_references_increase_score(self):
        router = self._make_router()
        body = "Change src/auth.py, src/models.py, tests/test_auth.py, config.yaml, README.md"
        result = router.analyze_complexity("Task", body, [])
        assert result.score >= 2
        assert any("file references" in r for r in result.reasons)

    def test_complex_title_keywords(self):
        router = self._make_router()
        result = router.analyze_complexity("Refactor authentication system", "", [])
        assert result.score >= 2
        assert any("complex keyword" in r for r in result.reasons)

    def test_simple_title_keywords(self):
        router = self._make_router()
        result = router.analyze_complexity("Fix typo in README", "", [])
        assert result.score == 0  # -1 clamped to 0
        assert any("simple keyword" in r for r in result.reasons)

    def test_score_clamped_to_10(self):
        router = self._make_router()
        # Stack all complexity signals
        body = (
            "x" * 3000
            + "\n"
            + "\n".join([f"- [x] Task {i}" for i in range(10)])
            + "\n"
            + "```\ncode\n```\n" * 5
        )
        body += " ".join([f"file{i}.py" for i in range(10)])
        result = router.analyze_complexity(
            "Refactor everything", body, ["refactor", "security"]
        )
        assert result.score <= 10

    def test_score_clamped_to_0(self):
        router = self._make_router()
        result = router.analyze_complexity(
            "Fix typo in docs", "", ["docs", "typo", "easy"]
        )
        assert result.score >= 0

    def test_threshold_determines_tier(self):
        router = self._make_router(threshold=3)
        # Score of 2 -> light
        result = router.analyze_complexity("Task", "x" * 2500, [])
        assert result.score >= 2
        # With low threshold, body alone might trigger heavy
        if result.score >= 3:
            assert result.tier == "heavy"
        else:
            assert result.tier == "light"

    def test_combined_signals(self):
        """Complex issue with multiple signals routes to heavy."""
        router = self._make_router(threshold=5)
        body = (
            "## Requirements\n"
            "- [x] Redesign the auth module\n"
            "- [ ] Update tests in tests/test_auth.py\n"
            "- [ ] Update config.yaml\n"
            "- [ ] Update docs/auth.md\n"
            "- [ ] Migration script\n"
            "\n```python\nclass AuthService:\n    pass\n```\n"
            "\nAffects: src/auth.py, src/middleware.py, config.yaml"
        )
        result = router.analyze_complexity(
            "Refactor authentication", body, ["refactor"]
        )
        assert result.score >= 5
        assert result.tier == "heavy"


# ---------------------------------------------------------------------------
# ModelRouter: Model Selection
# ---------------------------------------------------------------------------


class TestModelSelection:
    """Tests for ModelRouter.select_model."""

    def test_returns_none_when_disabled(self):
        from nebulus_swarm.config import RoutingConfig
        from nebulus_swarm.overlord.model_router import ModelRouter

        config = RoutingConfig(enabled=False)
        router = ModelRouter(config)
        result = router.select_model("title", "body", [])
        assert result is None

    def test_selects_light_model(self):
        from nebulus_swarm.config import ModelProfile, RoutingConfig
        from nebulus_swarm.overlord.model_router import ModelRouter

        config = RoutingConfig(
            enabled=True,
            complexity_threshold=5,
            models={
                "light": ModelProfile(name="small-8b", tier="light"),
                "heavy": ModelProfile(name="big-30b", tier="heavy"),
            },
        )
        router = ModelRouter(config)
        result = router.select_model("Fix typo", "", ["docs"])
        assert result.name == "small-8b"

    def test_selects_heavy_model(self):
        from nebulus_swarm.config import ModelProfile, RoutingConfig
        from nebulus_swarm.overlord.model_router import ModelRouter

        config = RoutingConfig(
            enabled=True,
            complexity_threshold=3,
            models={
                "light": ModelProfile(name="small-8b", tier="light"),
                "heavy": ModelProfile(name="big-30b", tier="heavy"),
            },
        )
        router = ModelRouter(config)
        body = "x" * 3000 + "\n- [x] task1\n- [ ] task2\n- [ ] task3"
        result = router.select_model("Refactor module", body, ["refactor"])
        assert result.name == "big-30b"

    def test_falls_back_to_default_tier(self):
        from nebulus_swarm.config import ModelProfile, RoutingConfig
        from nebulus_swarm.overlord.model_router import ModelRouter

        config = RoutingConfig(
            enabled=True,
            complexity_threshold=5,
            default_tier="heavy",
            models={
                "heavy": ModelProfile(name="big-30b", tier="heavy"),
                # No "light" model configured
            },
        )
        router = ModelRouter(config)
        result = router.select_model("Fix typo", "", ["docs"])
        # Light tier not found, falls back to default tier (heavy)
        assert result.name == "big-30b"

    def test_returns_none_when_no_models_configured(self):
        from nebulus_swarm.config import RoutingConfig
        from nebulus_swarm.overlord.model_router import ModelRouter

        config = RoutingConfig(enabled=True, models={})
        router = ModelRouter(config)
        result = router.select_model("Fix typo", "", [])
        assert result is None


# ---------------------------------------------------------------------------
# DockerManager: Model Override
# ---------------------------------------------------------------------------


class TestDockerManagerModelOverride:
    """Tests for DockerManager model override in spawn."""

    def test_build_env_default_model(self):
        from nebulus_swarm.config import LLMConfig, MinionConfig
        from nebulus_swarm.overlord.docker_manager import DockerManager

        manager = DockerManager(
            minion_config=MinionConfig(),
            llm_config=LLMConfig(
                base_url="http://default:5000/v1",
                model="default-model",
            ),
            github_token="tok",
            stub_mode=True,
        )
        env = manager._build_environment("m-1", "o/r", 1)
        assert env["NEBULUS_MODEL"] == "default-model"
        assert env["NEBULUS_BASE_URL"] == "http://default:5000/v1"

    def test_build_env_with_model_override(self):
        from nebulus_swarm.config import LLMConfig, ModelProfile, MinionConfig
        from nebulus_swarm.overlord.docker_manager import DockerManager

        manager = DockerManager(
            minion_config=MinionConfig(),
            llm_config=LLMConfig(
                base_url="http://default:5000/v1",
                model="default-model",
            ),
            github_token="tok",
            stub_mode=True,
        )
        override = ModelProfile(
            name="custom-8b",
            tier="light",
            base_url="http://custom:8080/v1",
            timeout=300,
        )
        env = manager._build_environment("m-1", "o/r", 1, model_override=override)
        assert env["NEBULUS_MODEL"] == "custom-8b"
        assert env["NEBULUS_BASE_URL"] == "http://custom:8080/v1"
        assert env["NEBULUS_TIMEOUT"] == "300"

    def test_build_env_override_inherits_base_url(self):
        """Model override with empty base_url inherits from default."""
        from nebulus_swarm.config import LLMConfig, ModelProfile, MinionConfig
        from nebulus_swarm.overlord.docker_manager import DockerManager

        manager = DockerManager(
            minion_config=MinionConfig(),
            llm_config=LLMConfig(
                base_url="http://default:5000/v1",
                model="default-model",
            ),
            github_token="tok",
            stub_mode=True,
        )
        override = ModelProfile(name="custom-8b", tier="light", base_url="")
        env = manager._build_environment("m-1", "o/r", 1, model_override=override)
        assert env["NEBULUS_MODEL"] == "custom-8b"
        assert env["NEBULUS_BASE_URL"] == "http://default:5000/v1"

    def test_spawn_minion_with_model_override(self):
        from nebulus_swarm.config import LLMConfig, ModelProfile, MinionConfig
        from nebulus_swarm.overlord.docker_manager import DockerManager

        manager = DockerManager(
            minion_config=MinionConfig(),
            llm_config=LLMConfig(),
            github_token="tok",
            stub_mode=True,
        )
        override = ModelProfile(name="routed-model", tier="light")
        minion_id = manager.spawn_minion("o/r", 1, model_override=override)
        assert minion_id.startswith("minion-")


# ---------------------------------------------------------------------------
# QueuedIssue: body field
# ---------------------------------------------------------------------------


class TestQueuedIssueBody:
    """Tests for QueuedIssue body field."""

    def test_queued_issue_has_body(self):
        from datetime import datetime

        from nebulus_swarm.overlord.github_queue import QueuedIssue

        issue = QueuedIssue(
            repo="o/r",
            number=1,
            title="Test",
            labels=["bug"],
            created_at=datetime.now(),
            body="Detailed description here.",
        )
        assert issue.body == "Detailed description here."

    def test_queued_issue_body_defaults_empty(self):
        from datetime import datetime

        from nebulus_swarm.overlord.github_queue import QueuedIssue

        issue = QueuedIssue(
            repo="o/r",
            number=1,
            title="Test",
            labels=[],
            created_at=datetime.now(),
        )
        assert issue.body == ""
