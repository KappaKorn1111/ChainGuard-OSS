from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from backend.app.integrations.contracts import IntegrationError, IntegrationErrorCategory
from pydantic import BaseModel, ConfigDict, Field

_SENSITIVE_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "CREDENTIAL")
_INTERPRETER_NAMES = {
    "ash",
    "bash",
    "dash",
    "env",
    "node",
    "perl",
    "python",
    "python3",
    "ruby",
    "sh",
    "zsh",
}


class ExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approved_executables: frozenset[Path]
    approved_working_roots: frozenset[Path]
    allowed_environment_keys: frozenset[str] = frozenset({"LANG", "LC_ALL", "PATH", "HOME"})
    timeout_seconds: float = Field(default=300, gt=0)
    max_output_bytes: int = Field(default=4 * 1024 * 1024, gt=0)
    max_memory_bytes: int | None = Field(default=1024 * 1024 * 1024, gt=0)
    max_cpu_seconds: int | None = Field(default=300, gt=0)
    max_file_bytes: int | None = Field(default=64 * 1024 * 1024, gt=0)
    allow_interpreters_for_testing: bool = False


class ExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executable: str
    arguments: list[str]
    working_directory: str
    environment: dict[str, str]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    exit_code: int | None
    stdout: bytes = Field(repr=False)
    stderr: bytes = Field(repr=False)
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False


@dataclass(frozen=True)
class ExecutionOutcome:
    record: ExecutionRecord


def _safe_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return {
        key: "[REDACTED]" if any(marker in key.upper() for marker in _SENSITIVE_MARKERS) else value
        for key, value in environment.items()
    }


def _resource_limiter(policy: ExecutionPolicy):
    if os.name != "posix":
        return None

    def set_limits() -> None:
        import resource

        os.setsid()
        if policy.max_memory_bytes:
            resource.setrlimit(
                resource.RLIMIT_AS, (policy.max_memory_bytes, policy.max_memory_bytes)
            )
        if policy.max_cpu_seconds:
            resource.setrlimit(
                resource.RLIMIT_CPU, (policy.max_cpu_seconds, policy.max_cpu_seconds)
            )
        if policy.max_file_bytes:
            resource.setrlimit(
                resource.RLIMIT_FSIZE, (policy.max_file_bytes, policy.max_file_bytes)
            )
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))

    return set_limits


class SecureProcessRunner:
    def __init__(self, policy: ExecutionPolicy) -> None:
        self.policy = policy
        self._approved_executables = {path.resolve() for path in policy.approved_executables}
        if not policy.allow_interpreters_for_testing and any(
            path.name.lower() in _INTERPRETER_NAMES
            or path.name.lower().startswith(("python", "node"))
            for path in self._approved_executables
        ):
            raise ValueError("shells and interpreters cannot be approved for production execution")
        self._approved_roots = {path.resolve() for path in policy.approved_working_roots}

    def run(
        self,
        executable: Path,
        arguments: Sequence[str],
        *,
        working_directory: Path,
        environment: Mapping[str, str] | None = None,
        cancel_event: Event | None = None,
    ) -> ExecutionOutcome:
        resolved_executable = executable.resolve(strict=True)
        if (
            not resolved_executable.is_file()
            or resolved_executable not in self._approved_executables
        ):
            raise IntegrationError(
                IntegrationErrorCategory.CONFIGURATION, "executable is not allowlisted"
            )
        cwd = working_directory.resolve(strict=True)
        within_approved_root = any(
            cwd == root or cwd.is_relative_to(root) for root in self._approved_roots
        )
        if not cwd.is_dir() or not within_approved_root:
            raise IntegrationError(
                IntegrationErrorCategory.INVALID_INPUT,
                "working directory is outside approved roots",
            )
        argv = [str(resolved_executable), *self._validate_arguments(arguments, cwd)]
        explicit_environment = self._build_environment(environment or {})
        started_at = datetime.now(UTC)
        started = time.monotonic()
        process = subprocess.Popen(  # noqa: S603 - executable and argv are allowlisted/validated
            argv,
            cwd=cwd,
            env=explicit_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=os.name != "posix",
            preexec_fn=_resource_limiter(self.policy),
        )
        stdout, stderr, timed_out, cancelled, truncated = self._capture(
            process, started, cancel_event
        )
        completed_at = datetime.now(UTC)
        record = ExecutionRecord(
            executable=str(resolved_executable),
            arguments=argv[1:],
            working_directory=str(cwd),
            environment=_safe_environment(explicit_environment),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=time.monotonic() - started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            cancelled=cancelled,
            output_truncated=truncated,
        )
        if timed_out:
            raise IntegrationError(
                IntegrationErrorCategory.TIMEOUT,
                "tool execution timed out",
                retryable=True,
                details={"record": record.model_dump(mode="json")},
            )
        if cancelled:
            raise IntegrationError(
                IntegrationErrorCategory.CANCELLED,
                "tool execution was cancelled",
                details={"record": record.model_dump(mode="json")},
            )
        if truncated:
            raise IntegrationError(
                IntegrationErrorCategory.INVALID_OUTPUT,
                "tool output exceeded the configured limit",
                details={"record": record.model_dump(mode="json")},
            )
        if process.returncode:
            raise IntegrationError(
                IntegrationErrorCategory.EXECUTION,
                "tool execution failed",
                details={"record": record.model_dump(mode="json")},
            )
        return ExecutionOutcome(record=record)

    def detect_version(
        self,
        executable: Path,
        version_arguments: Sequence[str],
        *,
        working_directory: Path,
    ) -> str:
        outcome = self.run(
            executable,
            version_arguments,
            working_directory=working_directory,
        )
        output = (outcome.record.stdout or outcome.record.stderr).decode(
            "utf-8", errors="replace"
        )
        version = output.splitlines()[0].strip() if output else ""
        if not version:
            raise IntegrationError(
                IntegrationErrorCategory.INVALID_OUTPUT,
                "tool version output was empty",
            )
        return version

    def _validate_arguments(self, arguments: Sequence[str], cwd: Path) -> list[str]:
        validated: list[str] = []
        for argument in arguments:
            if not isinstance(argument, str):
                raise IntegrationError(
                    IntegrationErrorCategory.INVALID_INPUT, "tool arguments must be strings"
                )
            if len(argument) > 8192 or any(char in argument for char in ("\x00", "\n", "\r")):
                raise IntegrationError(
                    IntegrationErrorCategory.INVALID_INPUT, "tool argument is invalid"
                )
            option_name = argument.split("=", 1)[0].lstrip("-").upper()
            if argument.startswith("-") and any(
                marker in option_name for marker in _SENSITIVE_MARKERS
            ):
                raise IntegrationError(
                    IntegrationErrorCategory.INVALID_INPUT,
                    "credentials must not be passed in tool arguments",
                )
            candidate = argument.split("=", 1)[-1]
            candidate_path = Path(candidate)
            if candidate_path.is_absolute() or candidate.startswith(("../", "./")):
                resolved_candidate = (
                    candidate_path.resolve(strict=False)
                    if candidate_path.is_absolute()
                    else (cwd / candidate_path).resolve(strict=False)
                )
                if not any(
                    resolved_candidate == root or resolved_candidate.is_relative_to(root)
                    for root in self._approved_roots
                ):
                    raise IntegrationError(
                        IntegrationErrorCategory.INVALID_INPUT,
                        "tool argument references a path outside approved roots",
                    )
            validated.append(argument)
        return validated

    def _build_environment(self, supplied: Mapping[str, str]) -> dict[str, str]:
        disallowed = set(supplied) - self.policy.allowed_environment_keys
        if disallowed:
            raise IntegrationError(
                IntegrationErrorCategory.INVALID_INPUT,
                "environment contains non-allowlisted keys",
                details={"keys": sorted(disallowed)},
            )
        base = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        base.update(supplied)
        return base

    def _capture(
        self, process: subprocess.Popen[bytes], started: float, cancel_event: Event | None
    ) -> tuple[bytes, bytes, bool, bool, bool]:
        assert process.stdout is not None
        assert process.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        timed_out = cancelled = truncated = False
        while selector.get_map():
            if cancel_event and cancel_event.is_set():
                cancelled = True
                self._terminate(process)
            if time.monotonic() - started > self.policy.timeout_seconds:
                timed_out = True
                self._terminate(process)
            for key, _ in selector.select(timeout=0.05):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = buffers[key.data]
                remaining = self.policy.max_output_bytes - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated = True
                    self._terminate(process)
            if (timed_out or cancelled or truncated) and process.poll() is not None:
                for registered in list(selector.get_map().values()):
                    selector.unregister(registered.fileobj)
        process.wait()
        return bytes(buffers["stdout"]), bytes(buffers["stderr"]), timed_out, cancelled, truncated

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
