"""Tests for the BaseWorker ABC and shared dataclasses."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from nebulus_swarm.overlord.workers.base import BaseWorker, WorkerConfig, WorkerResult


# --- Concrete test implementation ---


class DummyWorker(BaseWorker):
    """Minimal concrete worker for ABC contract testing."""

    worker_type = "dummy"

    def __init__(self, config: WorkerConfig, is_available: bool = True) -> None:
        super().__init__(config)
        self._available = is_available

    @property
    def available(self) -> bool:
        return self._available

    def execute(
        self,
        prompt: str,
        project_path: Path,
        task_type: str = "feature",
        model: Optional[str] = None,
    ) -> WorkerResult:
        selected = self._select_model(task_type, model)
        return WorkerResult(
            success=True,
            output=f"echo: {prompt}",
            model_used=selected,
            worker_type=self.worker_type,
        )


# --- WorkerConfig tests ---


class TestWorkerConfig:
    """Tests for WorkerConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = WorkerConfig()
        assert cfg.enabled is False
        assert cfg.binary_path == ""
        assert cfg.default_model == ""
        assert cfg.model_overrides == {}
        assert cfg.timeout == 600

    def test_custom_values(self) -> None:
        cfg = WorkerConfig(
            enabled=True,
            binary_path="/usr/bin/test",
            default_model="big-model",
            model_overrides={"review": "small"},
            timeout=120,
        )
        assert cfg.enabled is True
        assert cfg.timeout == 120


# --- WorkerResult tests ---


class TestWorkerResult:
    """Tests for WorkerResult dataclass."""

    def test_defaults(self) -> None:
        result = WorkerResult(success=True)
        assert result.success is True
        assert result.output == ""
        assert result.error is None
        assert result.duration == 0.0
        assert result.model_used == ""
        assert result.worker_type == ""

    def test_full_result(self) -> None:
        result = WorkerResult(
            success=False,
            output="partial",
            error="broke",
            duration=1.5,
            model_used="big",
            worker_type="test",
        )
        assert result.worker_type == "test"
        assert result.error == "broke"


# --- BaseWorker ABC contract ---


class TestBaseWorkerABC:
    """Tests for BaseWorker ABC contract via DummyWorker."""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            BaseWorker(WorkerConfig())  # type: ignore[abstract]

    def test_concrete_implementation(self) -> None:
        cfg = WorkerConfig(enabled=True, default_model="default")
        worker = DummyWorker(cfg)
        assert worker.available is True
        assert worker.worker_type == "dummy"

    def test_execute_returns_worker_result(self, tmp_path: Path) -> None:
        cfg = WorkerConfig(enabled=True, default_model="default")
        worker = DummyWorker(cfg)
        result = worker.execute("hello", tmp_path)
        assert isinstance(result, WorkerResult)
        assert result.success is True
        assert result.output == "echo: hello"
        assert result.worker_type == "dummy"

    def test_unavailable_worker(self) -> None:
        cfg = WorkerConfig(enabled=True)
        worker = DummyWorker(cfg, is_available=False)
        assert worker.available is False


# --- _select_model tests ---


class TestSelectModel:
    """Tests for BaseWorker._select_model priority chain."""

    def test_explicit_wins(self) -> None:
        cfg = WorkerConfig(
            default_model="default",
            model_overrides={"review": "override"},
        )
        worker = DummyWorker(cfg)
        assert worker._select_model("review", explicit="explicit") == "explicit"

    def test_override_for_task_type(self) -> None:
        cfg = WorkerConfig(
            default_model="default",
            model_overrides={"review": "override"},
        )
        worker = DummyWorker(cfg)
        assert worker._select_model("review") == "override"

    def test_falls_back_to_default(self) -> None:
        cfg = WorkerConfig(
            default_model="default",
            model_overrides={"review": "override"},
        )
        worker = DummyWorker(cfg)
        assert worker._select_model("feature") == "default"

    def test_empty_overrides(self) -> None:
        cfg = WorkerConfig(default_model="default")
        worker = DummyWorker(cfg)
        assert worker._select_model("anything") == "default"
