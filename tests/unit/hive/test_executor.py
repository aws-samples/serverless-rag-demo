import pytest
from hive_core.executor import CodeExecutor


@pytest.fixture
def executor(tmp_path):
    return CodeExecutor(workspace_dir=str(tmp_path), timeout=5)


def test_execute_simple_script(executor):
    result = executor.execute("print('hello world')")
    assert result.success is True
    assert "hello world" in result.stdout


def test_execute_returns_stderr_on_error(executor):
    result = executor.execute("raise ValueError('oops')")
    assert result.success is False
    assert "oops" in result.stderr


def test_execute_timeout(executor):
    executor.timeout = 1
    result = executor.execute("import time; time.sleep(10)")
    assert result.success is False
    assert "timed out" in result.stderr.lower() or "timeout" in result.stderr.lower()


def test_execute_captures_return_value(executor):
    result = executor.execute("x = 42\nprint(x)")
    assert "42" in result.stdout


def test_execute_with_saved_script(executor, tmp_path):
    script_path = tmp_path / "test_script.py"
    script_path.write_text("print('from file')")
    result = executor.execute_file(str(script_path))
    assert result.success is True
    assert "from file" in result.stdout
