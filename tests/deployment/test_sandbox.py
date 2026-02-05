import pytest
import os
from nebulus_atom.utils.sandbox import sandbox, SandboxViolation


@sandbox
def safe_write():
    # Attempt to write to .scratchpad (should pass)
    with open(".scratchpad/safe_test.txt", "w") as f:
        f.write("safe")


@sandbox
def unsafe_write():
    # Attempt to write outside (should fail)
    with open("unsafe_test.txt", "w") as f:
        f.write("unsafe")


def test_sandbox_allowed_write():
    """Verify writing to .scratchpad is allowed."""
    os.makedirs(".scratchpad", exist_ok=True)
    try:
        safe_write()
        assert os.path.exists(".scratchpad/safe_test.txt")
    finally:
        if os.path.exists(".scratchpad/safe_test.txt"):
            os.remove(".scratchpad/safe_test.txt")


def test_sandbox_denied_write():
    """Verify writing outside .scratchpad raises SandboxViolation."""
    with pytest.raises(SandboxViolation):
        unsafe_write()

    # Double check file wasn't created
    assert not os.path.exists("unsafe_test.txt")
