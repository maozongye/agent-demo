#!/usr/bin/env python3
"""Lightweight SQL migration runner (up/down).

Usage:
    python scripts/migrate.py up 001
    python scripts/migrate.py down 001
    python scripts/migrate.py up          # apply all pending up files in order

Reads POSTGRES_URL (or DATABASE_URL) from the environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"


def _dsn() -> str:
    dsn = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("POSTGRES_URL or DATABASE_URL must be set")
    return dsn


def _read_sql(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"Migration file not found: {path}")
    return path.read_text(encoding="utf-8")


def _apply(sql: str) -> None:
    try:
        import psycopg2
    except ImportError as exc:
        raise SystemExit("psycopg2 is required: pip install psycopg2-binary") from exc

    conn = psycopg2.connect(_dsn())
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _up_path(version: str) -> Path:
    matches = sorted(VERSIONS.glob(f"{version}_*.sql"))
    matches = [p for p in matches if not p.name.endswith("_down.sql")]
    if not matches:
        raise SystemExit(f"No up migration for version {version}")
    return matches[0]


def _down_path(version: str) -> Path:
    matches = sorted(VERSIONS.glob(f"{version}_*_down.sql"))
    if not matches:
        raise SystemExit(f"No down migration for version {version}")
    return matches[0]


def _list_versions() -> list[str]:
    versions = set()
    for p in VERSIONS.glob("*.sql"):
        if p.name.endswith("_down.sql"):
            continue
        versions.add(p.name.split("_", 1)[0])
    return sorted(versions)


def main(argv: list[str]) -> None:
    if len(argv) < 2 or argv[1] not in {"up", "down"}:
        raise SystemExit(__doc__)
    direction = argv[1]
    if len(argv) >= 3:
        versions = [argv[2]]
    else:
        if direction == "down":
            raise SystemExit("down requires an explicit VERSION")
        versions = _list_versions()

    for version in versions:
        path = _up_path(version) if direction == "up" else _down_path(version)
        print(f"Applying {direction} {path.name} ...")
        _apply(_read_sql(path))
        print(f"OK {path.name}")


if __name__ == "__main__":
    main(sys.argv)
