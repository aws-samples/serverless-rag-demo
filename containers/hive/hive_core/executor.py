import subprocess
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int


class CodeExecutor:
    """Sandboxed Python code executor using subprocess."""

    def __init__(self, workspace_dir: str, timeout: int = 30):
        self.workspace_dir = workspace_dir
        self.timeout = timeout

    def execute(self, code: str) -> ExecutionResult:
        """Execute Python code string in a subprocess."""
        script_path = os.path.join(self.workspace_dir, "_exec_tmp.py")
        with open(script_path, "w") as f:
            f.write(code)
        return self.execute_file(script_path)

    def execute_file(self, script_path: str) -> ExecutionResult:
        """Execute a Python script file in a subprocess."""
        try:
            result = subprocess.run(
                ["python", script_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.workspace_dir,
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Timed out after {self.timeout} seconds",
                return_code=-1,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
            )
