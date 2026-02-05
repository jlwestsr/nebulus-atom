import os
import builtins
import functools
from contextlib import contextmanager


class SandboxViolation(Exception):
    pass


def validate_path(path: str):
    """Ensure path is within .scratchpad/"""
    # Normalize path
    abs_path = os.path.abspath(path)
    cwd = os.getcwd()
    scratchpad_dir = os.path.join(cwd, ".scratchpad")

    # Allow reading from project root (for reading code), but WRITING only to scratchpad?
    # Phase 9 requirements say "Implement Sandboxed Execution for Skills".
    # Usually this means preventing skills from messing up the core agent.

    # Strict mode: Only allow access to .scratchpad
    if not abs_path.startswith(scratchpad_dir):
        # We might allow read-only access to specific system paths, but for now strict.
        raise SandboxViolation(
            f"Access denied: {path}. Skills are restricted to .scratchpad/"
        )


# Mock Open
original_open = builtins.open


@contextmanager
def restricted_open(
    file,
    mode="r",
    buffering=-1,
    encoding=None,
    errors=None,
    newline=None,
    closefd=True,
    opener=None,
):
    # If writing, strictly enforce sandbox
    if "w" in mode or "a" in mode or "+" in mode:
        validate_path(file)

    # If reading, we might be more lenient (agent needs to read its own code?)
    # For now, let's enforce strict sandbox for simplicity and safety as per plan.
    validate_path(file)

    f = original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)
    try:
        yield f
    finally:
        f.close()


def sandbox(func):
    """
    Decorator to execute a function in a restricted environment.
    Patches: open
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Patch open
        # Note: This is thread-unsafe and basic. production sandbox would use seccomp/containers.
        with patch_builtins():
            return func(*args, **kwargs)

    return wrapper


@contextmanager
def patch_builtins():
    # We can't easily patch builtins.open globally without affecting other threads
    # But for synchronous skill execution it works.

    # For a robust approach we'd use 'unittest.mock.patch' logic manually
    # But here is a simple swap
    builtins.open = restricted_open
    try:
        yield
    finally:
        builtins.open = original_open
