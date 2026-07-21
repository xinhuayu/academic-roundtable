from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def safe_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Supported files are PDF, TXT, and Markdown")
    return extension


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, page_number: int | None, target_chars: int = 2200) -> list[dict[str, Any]]:
    text = normalize_text(text)
    if not text:
        return []
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[dict[str, Any]] = []
    current: list[str] = []
    current_size = 0
    for paragraph in paragraphs:
        if current and current_size + len(paragraph) > target_chars:
            chunks.append({"page_number": page_number, "content": "\n\n".join(current)})
            overlap = current[-1:] if len(current[-1]) < 500 else []
            current = overlap.copy()
            current_size = sum(len(item) for item in current)
        if len(paragraph) > target_chars * 2:
            for start in range(0, len(paragraph), target_chars):
                piece = paragraph[start : start + target_chars]
                if current:
                    chunks.append({"page_number": page_number, "content": "\n\n".join(current)})
                    current, current_size = [], 0
                chunks.append({"page_number": page_number, "content": piece})
        else:
            current.append(paragraph)
            current_size += len(paragraph)
    if current:
        chunks.append({"page_number": page_number, "content": "\n\n".join(current)})
    return chunks


def extract_passages(path: Path) -> list[dict[str, Any]]:
    extension = path.suffix.lower()
    if extension == ".pdf":
        reader = PdfReader(str(path))
        passages: list[dict[str, Any]] = []
        for page_index, page in enumerate(reader.pages, start=1):
            passages.extend(chunk_text(page.extract_text() or "", page_index))
        return passages
    text = path.read_text(encoding="utf-8", errors="replace")
    return chunk_text(text, None)


def group_passages_for_digest(
    passages: list[dict[str, Any]], max_chars: int = 30000
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for passage in passages:
        content_size = len(passage["content"])
        if current and size + content_size > max_chars:
            groups.append(current)
            current, size = [], 0
        current.append(passage)
        size += content_size
    if current:
        groups.append(current)
    return groups


def format_passage_group(group: list[dict[str, Any]], filename: str) -> str:
    parts = []
    for passage in group:
        locator = f"page {passage['page_number']}" if passage.get("page_number") else "text section"
        parts.append(f"[{filename}, {locator}]\n{passage['content']}")
    return "\n\n---\n\n".join(parts)
