from __future__ import annotations

from pathlib import Path

import pytest

import app.server_runtime as server_runtime
from app.services.namespace_deletion_jobs import create_namespace_deletion_job
from app.services.namespace_deletion_jobs import load_namespace_deletion_job
from app.services.namespace_deletion_jobs import mark_namespace_deletion_job_failed
from app.services.namespace_deletion_jobs import mark_namespace_deletion_job_succeeded


def test_namespace_deletion_job_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_runtime, "_DEFAULT_DATABASE_DIRECTORY", tmp_path)
    monkeypatch.setattr(server_runtime, "_DEFAULT_RUNTIME_DIRECTORY", tmp_path / "runtime")

    job_record = create_namespace_deletion_job(
        deleted_namespace="cla",
        redirect_namespace="default",
    )

    loaded_pending = load_namespace_deletion_job(job_id=job_record["job_id"])
    assert loaded_pending is not None
    assert loaded_pending["status"] == "pending"
    assert loaded_pending["deleted_namespace"] == "cla"
    assert loaded_pending["redirect_namespace"] == "default"
    assert loaded_pending["error"] == ""

    mark_namespace_deletion_job_failed(
        job_id=job_record["job_id"],
        error="boom",
    )
    loaded_failed = load_namespace_deletion_job(job_id=job_record["job_id"])
    assert loaded_failed is not None
    assert loaded_failed["status"] == "failed"
    assert loaded_failed["error"] == "boom"

    mark_namespace_deletion_job_succeeded(job_id=job_record["job_id"])
    loaded_succeeded = load_namespace_deletion_job(job_id=job_record["job_id"])
    assert loaded_succeeded is not None
    assert loaded_succeeded["status"] == "succeeded"
    assert loaded_succeeded["error"] == ""
