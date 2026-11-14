import concurrent.futures
import sys
import time
from pathlib import Path
from threading import Event

import pytest

from backend.app.integrations.contracts import (
    IntegrationError,
    IntegrationErrorCategory,
)
from backend.app.integrations.execution import ExecutionPolicy, SecureProcessRunner


def runner(
    tmp_path: Path,
    *,
    timeout: float = 2,
    max_output: int = 4096,
    environment_keys: frozenset[str] = frozenset({"API_TOKEN"}),
) -> SecureProcessRunner:
    return SecureProcessRunner(
        ExecutionPolicy(
            approved_executables=frozenset({Path(sys.executable)}),
            approved_working_roots=frozenset({tmp_path}),
            allowed_environment_keys=environment_keys,
            timeout_seconds=timeout,
            max_output_bytes=max_output,
            allow_interpreters_for_testing=True,
        )
    )


def test_production_policy_rejects_interpreters(tmp_path: Path) -> None:
    policy = ExecutionPolicy(
        approved_executables=frozenset({Path(sys.executable)}),
        approved_working_roots=frozenset({tmp_path}),
    )
    with pytest.raises(ValueError, match="interpreters"):
        SecureProcessRunner(policy)


def test_argument_array_prevents_shell_injection(tmp_path: Path) -> None:
    marker = tmp_path / "injected"
    malicious = f"; touch {marker}"
    result = runner(tmp_path).run(
        Path(sys.executable),
        ["-c", "import sys; print(sys.argv[1])", malicious],
        working_directory=tmp_path,
    )
    assert malicious.encode() in result.record.stdout
    assert not marker.exists()


def test_non_allowlisted_executable_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(IntegrationError, match="not allowlisted") as error:
        runner(tmp_path).run(Path("/bin/sh"), ["-c", "true"], working_directory=tmp_path)
    assert error.value.category == IntegrationErrorCategory.CONFIGURATION


def test_arguments_cannot_expose_credentials_or_escape_working_root(tmp_path: Path) -> None:
    with pytest.raises(IntegrationError, match="credentials"):
        runner(tmp_path).run(
            Path(sys.executable),
            ["--api-token=sensitive"],
            working_directory=tmp_path,
        )
    with pytest.raises(IntegrationError, match="outside approved roots"):
        runner(tmp_path).run(
            Path(sys.executable),
            ["/etc/passwd"],
            working_directory=tmp_path,
        )


def test_timeout_returns_safe_structured_record(tmp_path: Path) -> None:
    with pytest.raises(IntegrationError, match="timed out") as error:
        runner(tmp_path, timeout=0.05).run(
            Path(sys.executable),
            ["-c", "import time; time.sleep(2)"],
            working_directory=tmp_path,
        )
    assert error.value.category == IntegrationErrorCategory.TIMEOUT
    assert error.value.details["record"]["timed_out"] is True


def test_environment_is_minimal_and_secrets_are_redacted(tmp_path: Path) -> None:
    result = runner(tmp_path).run(
        Path(sys.executable),
        ["-c", "print('ok')"],
        working_directory=tmp_path,
        environment={"API_TOKEN": "do-not-record"},
    )
    assert result.record.environment == {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "API_TOKEN": "[REDACTED]",
    }


def test_cancellation_terminates_process(tmp_path: Path) -> None:
    cancellation = Event()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(
            runner(tmp_path, timeout=5).run,
            Path(sys.executable),
            ["-c", "import time; time.sleep(3)"],
            working_directory=tmp_path,
            cancel_event=cancellation,
        )
        time.sleep(0.1)
        cancellation.set()
        with pytest.raises(IntegrationError, match="cancelled") as error:
            future.result(timeout=2)
    assert error.value.category == IntegrationErrorCategory.CANCELLED


def test_output_cap_terminates_noisy_process(tmp_path: Path) -> None:
    with pytest.raises(IntegrationError, match="output exceeded") as error:
        runner(tmp_path, max_output=32).run(
            Path(sys.executable),
            ["-c", "print('x' * 1000)"],
            working_directory=tmp_path,
        )
    assert error.value.category == IntegrationErrorCategory.INVALID_OUTPUT


def test_version_detection_uses_the_same_execution_policy(tmp_path: Path) -> None:
    version = runner(tmp_path).detect_version(
        Path(sys.executable),
        ["--version"],
        working_directory=tmp_path,
    )
    assert version.startswith("Python ")
