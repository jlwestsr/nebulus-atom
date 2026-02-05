"""Tests for LLM connection pool."""

import threading
import time

import pytest

# Skip tests if openai is not installed
openai = pytest.importorskip("openai")

from nebulus_swarm.overlord.llm_pool import (  # noqa: E402
    DEFAULT_CONCURRENCY,
    LLMPool,
    PoolConfig,
)


def test_pool_config_defaults():
    """Test default pool configuration values."""
    config = PoolConfig(base_url="http://localhost:5000/v1", model="test-model")

    assert config.base_url == "http://localhost:5000/v1"
    assert config.model == "test-model"
    assert config.api_key == "not-needed"
    assert config.timeout == 600
    assert config.max_concurrency == DEFAULT_CONCURRENCY
    assert config.max_concurrency == 2  # Verify default is 2
    assert config.acquire_timeout == 60.0


def test_pool_config_from_env(monkeypatch):
    """Test pool config creation from environment variables."""
    monkeypatch.setenv("ATOM_LLM_BASE_URL", "http://test:8000/v1")
    monkeypatch.setenv("ATOM_LLM_MODEL", "custom-model")
    monkeypatch.setenv("ATOM_LLM_API_KEY", "test-key")
    monkeypatch.setenv("ATOM_LLM_TIMEOUT", "900")
    monkeypatch.setenv("ATOM_LLM_CONCURRENCY", "5")

    config = PoolConfig.from_env()

    assert config.base_url == "http://test:8000/v1"
    assert config.model == "custom-model"
    assert config.api_key == "test-key"
    assert config.timeout == 900
    assert config.max_concurrency == 5
    assert config.acquire_timeout == 60.0


def test_acquire_and_release():
    """Test acquiring and releasing a pool slot."""
    config = PoolConfig(base_url="http://localhost:5000/v1", model="test-model")
    pool = LLMPool(config)

    # Initial stats
    stats = pool.stats
    assert stats.active == 0
    assert stats.waiting == 0
    assert stats.total_requests == 0

    # Acquire a slot
    acquired = pool.acquire()
    assert acquired is True

    stats = pool.stats
    assert stats.active == 1
    assert stats.waiting == 0
    assert stats.total_requests == 1

    # Release the slot
    pool.release()

    stats = pool.stats
    assert stats.active == 0
    assert stats.waiting == 0
    assert stats.total_requests == 1


def test_acquire_respects_concurrency():
    """Test that acquire respects max_concurrency limit."""
    config = PoolConfig(
        base_url="http://localhost:5000/v1",
        model="test-model",
        max_concurrency=1,
    )
    pool = LLMPool(config)

    # First acquire should succeed
    acquired1 = pool.acquire()
    assert acquired1 is True

    # Second acquire should timeout with short timeout
    config2 = PoolConfig(
        base_url="http://localhost:5000/v1",
        model="test-model",
        max_concurrency=1,
        acquire_timeout=0.1,  # Short timeout
    )
    pool2 = LLMPool(config2)

    # Manually acquire the semaphore to block
    pool2.acquire()

    # Second acquire should fail
    acquired2 = pool2.acquire()
    assert acquired2 is False


def test_acquire_blocks_then_succeeds():
    """Test that acquire blocks and succeeds when slot becomes available."""
    config = PoolConfig(
        base_url="http://localhost:5000/v1",
        model="test-model",
        max_concurrency=1,
    )
    pool = LLMPool(config)

    acquired_by_thread2 = threading.Event()

    def thread1():
        """Hold the slot briefly then release."""
        pool.acquire()
        time.sleep(0.2)
        pool.release()

    def thread2():
        """Wait to acquire after thread1 releases."""
        time.sleep(0.1)  # Ensure thread1 acquires first
        success = pool.acquire()
        if success:
            acquired_by_thread2.set()
            pool.release()

    t1 = threading.Thread(target=thread1)
    t2 = threading.Thread(target=thread2)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # Thread 2 should have successfully acquired after thread 1 released
    assert acquired_by_thread2.is_set()


def test_stats_tracking():
    """Test that pool statistics are tracked correctly."""
    config = PoolConfig(base_url="http://localhost:5000/v1", model="test-model")
    pool = LLMPool(config)

    # Initial state
    stats = pool.stats
    assert stats.active == 0
    assert stats.total_requests == 0
    assert stats.total_errors == 0
    assert stats.total_retries == 0

    # Acquire
    pool.acquire()
    stats = pool.stats
    assert stats.active == 1
    assert stats.total_requests == 1

    # Record error
    pool.record_error()
    stats = pool.stats
    assert stats.total_errors == 1

    # Record retry
    pool.record_retry()
    stats = pool.stats
    assert stats.total_retries == 1

    # Release
    pool.release()
    stats = pool.stats
    assert stats.active == 0


def test_shutdown_prevents_acquire():
    """Test that shutdown prevents new acquisitions."""
    config = PoolConfig(base_url="http://localhost:5000/v1", model="test-model")
    pool = LLMPool(config)

    # Should acquire successfully
    acquired1 = pool.acquire()
    assert acquired1 is True
    pool.release()

    # Shutdown the pool
    pool.shutdown()

    # Should fail to acquire
    acquired2 = pool.acquire()
    assert acquired2 is False


def test_pool_has_client():
    """Test that pool creates and exposes OpenAI client."""
    config = PoolConfig(base_url="http://localhost:5000/v1", model="test-model")
    pool = LLMPool(config)

    client = pool.client
    assert client is not None
    assert isinstance(client, openai.OpenAI)
    # OpenAI may add trailing slash
    assert "localhost:5000/v1" in str(client.base_url)


def test_concurrent_access():
    """Test concurrent access with max_concurrency limit."""
    config = PoolConfig(
        base_url="http://localhost:5000/v1",
        model="test-model",
        max_concurrency=2,
    )
    pool = LLMPool(config)

    max_active = {"value": 0}
    lock = threading.Lock()

    def worker(worker_id: int):
        """Simulate work with the pool."""
        pool.acquire()

        # Track max active
        stats = pool.stats
        with lock:
            if stats.active > max_active["value"]:
                max_active["value"] = stats.active

        # Simulate work
        time.sleep(0.1)

        pool.release()

    # Spawn 5 threads
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    # Verify no more than 2 were active at once
    assert max_active["value"] <= 2
    assert max_active["value"] > 0  # At least some were active

    # All should have completed
    final_stats = pool.stats
    assert final_stats.active == 0
    assert final_stats.total_requests == 5
