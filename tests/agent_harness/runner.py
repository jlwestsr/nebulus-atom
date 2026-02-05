import subprocess
import sys
import time
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    duration: float


class AgentRunner:
    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()
        self.python_executable = sys.executable

    def run_agent(self, prompt: str, timeout: int = 60) -> RunResult:
        """
        Runs the agent with the given prompt in a subprocess.
        Waits for completion or timeout.
        """
        start_time = time.time()

        session_id = f"test_{int(time.time())}_{os.urandom(2).hex()}"

        # Command to run: python3 -m nebulus_atom.main start "<prompt>" --session-id <id>
        cmd = [
            self.python_executable,
            "-m",
            "nebulus_atom.main",
            "start",
            prompt,
            "--session-id",
            session_id,
        ]

        try:
            # Run process and capture output
            # We use text=True to get strings instead of bytes
            proc = subprocess.run(
                cmd,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    **os.environ,
                    "PYTHONUNBUFFERED": "1",
                    "MINI_NEBULUS_HEADLESS": "1",
                },
            )

            duration = time.time() - start_time
            return RunResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                duration=duration,
            )

        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            # Return partial output if available (capturing stdout/stderr from timeout exception is tricky in run(),
            # usually requires Popen for streaming, but run() returns bytes on timeout in e.stdout/stderr if configured)
            return RunResult(
                stdout=e.stdout or "[TIMEOUT]",
                stderr=e.stderr or "[TIMEOUT]",
                exit_code=-1,
                duration=duration,
            )
