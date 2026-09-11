"""Tenant-isolated local file storage for contract uploads."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.core.config import settings


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(filename: str) -> str:
    base = Path(filename).name
    cleaned = _SAFE_NAME.sub("_", base).strip("._")
    return cleaned or "upload.bin"


def tenant_root(tenant_id: int) -> Path:
    root = (settings.UPLOAD_DIR / str(tenant_id)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_tenant_upload(tenant_id: int, filename: str, data: bytes) -> str:
    """Save bytes under the tenant directory; return relative file_ref."""
    if not data:
        raise ValueError("Empty upload")
    safe = _safe_filename(filename)
    rel = f"{tenant_id}/{uuid.uuid4().hex}_{safe}"
    path = (settings.UPLOAD_DIR / rel).resolve()
    root = tenant_root(tenant_id)
    if not str(path).startswith(str(root)):
        raise PermissionError("Invalid upload path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def resolve_tenant_file(tenant_id: int, file_ref: str) -> Path:
    """Resolve a file_ref ensuring it stays inside the tenant directory."""
    if not file_ref or ".." in file_ref or file_ref.startswith("/"):
        raise PermissionError("Invalid file reference")
    path = (settings.UPLOAD_DIR / file_ref).resolve()
    root = tenant_root(tenant_id)
    if not str(path).startswith(str(root) + "/") and path != root:
        # must be under tenant root
        if not str(path).startswith(str(root)):
            raise PermissionError("Cross-tenant file access denied")
    expected_prefix = f"{tenant_id}/"
    if not file_ref.startswith(expected_prefix):
        raise PermissionError("Cross-tenant file access denied")
    return path


def read_tenant_file(tenant_id: int, file_ref: str) -> bytes:
    path = resolve_tenant_file(tenant_id, file_ref)
    if not path.is_file():
        raise FileNotFoundError(file_ref)
    return path.read_bytes()
