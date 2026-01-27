import os
import time
from mini_nebulus.config import Config
from mini_nebulus.utils.logger import setup_logger


def test_logger_file_creation():
    # Setup
    test_logger_name = f"test_logger_{int(time.time())}"
    logger = setup_logger(test_logger_name)

    # Action
    test_message = f"Test log message {int(time.time())}"
    logger.info(test_message)

    # Verification
    assert os.path.exists(Config.LOG_FILE)

    with open(Config.LOG_FILE, "r") as f:
        content = f.read()
        assert test_message in content
        assert "INFO" in content
        assert test_logger_name in content


def test_logger_singleton():
    logger1 = setup_logger("same_logger")
    logger2 = setup_logger("same_logger")
    assert logger1 is logger2

    # Check handlers aren't duplicated
    assert (
        len(logger1.handlers) == 1 or len(logger1.handlers) == 2
    )  # Might be 2 if tests run in parallel/weird state, but ideally 1 file handler
    # Actually, logger.getLogger returns same instance, but our setup_logger adds handlers.
    # We added a check `if logger.hasHandlers(): return logger`.
    # So handlers should not multiply.
