from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, Field


class ArtifactPathError(ValueError):
    """Raised when an artifact path attempts to escape the configured root."""


class ArtifactManifestItem(BaseModel):
    artifact_id: str
    run_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    type: str
    title: str
    path: str
    created_at: str | None = None
    summary: str = ""
    size_bytes: int | None = None
    content_type: str | None = None
    preview_url: str | None = None
    download_url: str | None = None


class ArtifactManifestResponse(BaseModel):
    root: str
    artifacts: list[ArtifactManifestItem] = Field(default_factory=list)


def read_artifact_manifests(root: str | Path) -> ArtifactManifestResponse:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        return ArtifactManifestResponse(root=str(base), artifacts=[])

    artifacts: list[ArtifactManifestItem] = []
    for manifest_path in sorted(base.glob("**/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = data if isinstance(data, list) else [data]
        for item in items:
            relative_path = str(item.get("path", "")).replace("\\", "/")
            resolved = (manifest_path.parent / relative_path).resolve()
            try:
                path_inside_root = resolved.relative_to(base)
            except ValueError:
                continue
            artifacts.append(
                ArtifactManifestItem(
                    **{
                        **item,
                        **_artifact_file_metadata(path_inside_root, resolved),
                    }
                )
            )
    return ArtifactManifestResponse(root=str(base), artifacts=artifacts)


def resolve_artifact_file(root: str | Path, artifact_path: str) -> Path:
    base = Path(root).expanduser().resolve()
    normalized = artifact_path.replace("\\", "/").lstrip("/")
    resolved = (base / normalized).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ArtifactPathError("artifact path escapes root") from exc
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(normalized)
    return resolved


def _artifact_file_metadata(relative_path: Path, resolved: Path) -> dict[str, Any]:
    path = str(relative_path).replace("\\", "/")
    content_type = mimetypes.guess_type(path)[0]
    encoded_path = quote(path, safe="/")
    return {
        "path": path,
        "size_bytes": resolved.stat().st_size if resolved.exists() and resolved.is_file() else None,
        "content_type": content_type,
        "preview_url": f"/api/artifacts/files/{encoded_path}",
        "download_url": f"/api/artifacts/files/{encoded_path}?download=1",
    }
