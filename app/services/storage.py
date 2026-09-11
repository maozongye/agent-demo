"""Tenant-isolated local file storage for contract and knowledge uploads."""

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
    root = tenant_root(tenant_id)
    path = (settings.UPLOAD_DIR / rel).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Invalid upload path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def resolve_tenant_file(tenant_id: int, file_ref: str) -> Path:
    """Resolve a file_ref ensuring it stays inside the tenant directory."""
    if not file_ref or file_ref.startswith("/") or ".." in Path(file_ref).parts:
        raise PermissionError("Invalid file reference")
    expected_prefix = f"{tenant_id}/"
    if not file_ref.startswith(expected_prefix):
        raise PermissionError("Cross-tenant file access denied")
    root = tenant_root(tenant_id)
    path = (settings.UPLOAD_DIR / file_ref).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Cross-tenant file access denied")
    return path


def read_tenant_file(tenant_id: int, file_ref: str) -> bytes:
    path = resolve_tenant_file(tenant_id, file_ref)
    if not path.is_file():
        raise FileNotFoundError(file_ref)
    return path.read_bytes()


def save_tenant_kb_upload(tenant_id: int, kb_id: int, filename: str, data: bytes) -> str:
    """Save bytes under ``{tenant_id}/kb/{kb_id}/``; return relative file_ref."""
    if not data:
        raise ValueError("Empty upload")
    if int(kb_id) <= 0:
        raise ValueError("Invalid knowledge base id")
    safe = _safe_filename(filename)
    rel = f"{tenant_id}/kb/{int(kb_id)}/{uuid.uuid4().hex}_{safe}"
    root = tenant_root(tenant_id)
    path = (settings.UPLOAD_DIR / rel).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Invalid upload path")
    # Must stay under kb/{kb_id}/
    kb_root = (root / "kb" / str(int(kb_id))).resolve()
    if not path.is_relative_to(kb_root):
        raise PermissionError("Invalid knowledge-base upload path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel
