import pytest
import os
from tests.agent_harness.runner import AgentRunner

SCRATCHPAD = ".scratchpad"


@pytest.fixture(scope="module")
def runner():
    """Provides an AgentRunner instance."""
    return AgentRunner()


@pytest.fixture(autouse=True)
def cleanup_scratchpad():
    """Ensures scratchpad exists and cleans up test artifacts."""
    os.makedirs(SCRATCHPAD, exist_ok=True)
    yield
    # Optional: Clean up after test? keeping for inspection for now.
    # shutil.rmtree(SCRATCHPAD)


def test_file_creation(runner):
    """
    Goal: Verify the agent can create a simple file from a prompt.
    Prompt: "Create a file named .scratchpad/harness_test.txt with the content 'passed'."
    """
    target_file = os.path.join(SCRATCHPAD, "harness_test.txt")
    if os.path.exists(target_file):
        os.remove(target_file)

    prompt = f"Create a file named {target_file} with the EXACT content 'passed'. Do nothing else."

    print(f"\n[TEST] Running: {prompt}")
    result = runner.run_agent(prompt)

    print(f"[RESULT] Exit Code: {result.exit_code}")
    print(f"[STDOUT] {result.stdout}")  # Print FULL stdout for debugging
    print(f"[STDERR] {result.stderr}")

    assert result.exit_code == 0, "Agent process failed or crashed"
    assert os.path.exists(target_file), "Agent failed to create the target file"

    with open(target_file, "r") as f:
        content = f.read().strip()
    assert "passed" in content, f"File content mismatch. Got: {content}"


def test_context_resilience(runner):
    """
    Goal: Verify reading a large markdown file does NOT cause a 400 Bad Request (Context Overflow).
    Prompt: "Read AI_DIRECTIVES.md and tell me its size."
    """
    prompt = "Read AI_DIRECTIVES.md and tell me how many lines it has."

    print(f"\n[TEST] Running: {prompt}")
    result = runner.run_agent(prompt)

    print(f"[RESULT] Exit Code: {result.exit_code}")
    # We check for the specific crash signature from logs
    assert (
        "Chat completion aborted" not in result.stderr
    ), "Agent crashed with Context Overflow"
    assert result.exit_code == 0


def test_json_stability(runner):
    """
    Goal: Verify 'run_shell_command' does not loop with 'No command provided'.
    Prompt: "Run 'ls -l' in the .scratchpad directory."
    """
    prompt = "Run 'ls -l' in the .scratchpad directory."

    print(f"\n[TEST] Running: {prompt}")
    result = runner.run_agent(prompt)

    assert result.exit_code == 0
    assert (
        "Error: No command provided" not in result.stdout
    ), "Agent hit the Infinite Loop / JSON Hallucination bug"
    assert (
        "passed" in result.stdout
        or "total" in result.stdout
        or "harness_test" in result.stdout
    ), "Expected ls output not found in stdout"
