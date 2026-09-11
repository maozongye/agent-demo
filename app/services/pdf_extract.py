"""PDF text extraction for contract review."""

from __future__ import annotations

import io

from pypdf import PdfReader


def extract_text_from_pdf(data: bytes) -> str:
    """Extract text from PDF bytes.

    Raises:
        ValueError: If the PDF is empty, unreadable, or has no extractable text.
    """
    if not data:
        raise ValueError("PDF is empty")
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - surface as bad PDF
        raise ValueError(f"Invalid PDF: {exc}") from exc
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Encrypted PDF is not supported") from exc
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("PDF has no extractable text")
    return text
