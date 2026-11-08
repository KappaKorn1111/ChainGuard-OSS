from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest

from worker import tasks


class FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_dependency_track_receives_native_cyclonedx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sbom = tmp_path / "syft.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX","specVersion":"1.6"}')
    observed: dict = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            observed["client"] = kwargs

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, path: str, *, data: dict, files: dict) -> FakeResponse:
            observed["post_path"] = path
            observed["data"] = data
            filename, handle, content_type = files["bom"]
            observed["file"] = (filename, handle.read(), content_type)
            return FakeResponse()

        def get(self, path: str, *, params: dict) -> FakeResponse:
            observed["get"] = (path, params)
            return FakeResponse({"uuid": "7cd0fa28-eab2-4f86-8668-d08fcf4d74f8"})

    monkeypatch.setattr(
        tasks,
        "settings",
        SimpleNamespace(
            dependency_track_enabled=True,
            dependency_track_url="http://dependency-track-api:8080",
            dependency_track_api_key="test-only-key",
            dependency_track_project_name="ChainGuard OSS",
            dependency_track_project_version="continuous",
        ),
    )
    monkeypatch.setattr(tasks.httpx, "Client", FakeClient)

    project_uuid = tasks.submit_dependency_track(sbom, "job-id")

    assert project_uuid == "7cd0fa28-eab2-4f86-8668-d08fcf4d74f8"
    assert observed["post_path"] == "/api/v1/bom"
    assert observed["file"] == (
        "sbom.cdx.json",
        b'{"bomFormat":"CycloneDX","specVersion":"1.6"}',
        "application/vnd.cyclonedx+json",
    )
