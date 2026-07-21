from __future__ import annotations

import importlib.util
import importlib.metadata
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any


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


def chunk_text(
    text: str,
    page_number: int | None,
    target_chars: int = 2200,
    section: str | None = None,
) -> list[dict[str, Any]]:
    text = normalize_text(text)
    if not text:
        return []
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[dict[str, Any]] = []
    current: list[str] = []
    current_size = 0
    for paragraph in paragraphs:
        if current and current_size + len(paragraph) > target_chars:
            chunks.append(
                {
                    "page_number": page_number,
                    "section": section,
                    "content": "\n\n".join(current),
                }
            )
            overlap = current[-1:] if len(current[-1]) < 500 else []
            current = overlap.copy()
            current_size = sum(len(item) for item in current)
        if len(paragraph) > target_chars * 2:
            for start in range(0, len(paragraph), target_chars):
                piece = paragraph[start : start + target_chars]
                if current:
                    chunks.append(
                        {
                            "page_number": page_number,
                            "section": section,
                            "content": "\n\n".join(current),
                        }
                    )
                    current, current_size = [], 0
                chunks.append({"page_number": page_number, "section": section, "content": piece})
        else:
            current.append(paragraph)
            current_size += len(paragraph)
    if current:
        chunks.append(
            {
                "page_number": page_number,
                "section": section,
                "content": "\n\n".join(current),
            }
        )
    return chunks


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _module_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except Exception:
        if name == "pymupdf":
            try:
                import fitz  # type: ignore

                return getattr(fitz, "__version__", None)
            except Exception:
                pass
        return None


def extract_dependency_health() -> dict[str, bool | str | None]:
    has_pymupdf = _has_module("fitz") or _has_module("pymupdf")
    return {
        "pymupdf": has_pymupdf,
        "pdfplumber": _has_module("pdfplumber"),
        "pypdf": _has_module("pypdf"),
        "pymupdf_version": _module_version("pymupdf") if has_pymupdf else None,
        "pdfplumber_version": _module_version("pdfplumber"),
        "pypdf_version": _module_version("pypdf"),
    }


def _safe_table_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    return text if text else ""


def _markdown_table(rows: Iterable[Iterable[Any]]) -> str:
    normalized_rows = [
        [_safe_table_cell(cell) for cell in row]
        for row in rows
    ]
    if not normalized_rows:
        return ""
    column_count = max(len(row) for row in normalized_rows)
    padded_rows: list[list[str]] = []
    for row in normalized_rows:
        padded_row = row + [""] * (column_count - len(row))
        if any(cell.strip() for cell in padded_row):
            padded_rows.append(padded_row)
    if not padded_rows:
        return ""
    widths = [1] * column_count
    for row in padded_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def row_to_markdown(row: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) + " |"

    header = row_to_markdown(padded_rows[0])
    separator = "| " + " | ".join("-" * max(3, width) for width in widths) + " |"
    body = [row_to_markdown(row) for row in padded_rows[1:]]
    return "\n".join([header, separator, *body])


def _extract_pdf_tables_with_pdfplumber(
    page: Any,
    page_number: int,
    seen_tables: set[tuple[tuple[str, ...], ...]] | None = None,
) -> list[dict[str, Any]]:
    if seen_tables is None:
        seen_tables = set()
    passages: list[dict[str, Any]] = []
    table_counter = 0
    table_strategies: list[dict[str, Any] | None] = [
        None,
        {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
            "join_tolerance": 3,
        },
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "min_words_vertical": 2,
            "min_words_horizontal": 2,
            "intersection_x_tolerance": 2,
            "intersection_y_tolerance": 2,
        },
        {
            "vertical_strategy": "lines_strict",
            "horizontal_strategy": "lines_strict",
            "snap_tolerance": 2,
            "join_tolerance": 2,
        },
        {
            "vertical_strategy": "text",
            "horizontal_strategy": "lines",
            "min_words_vertical": 3,
            "min_words_horizontal": 3,
            "intersection_x_tolerance": 3,
            "intersection_y_tolerance": 3,
        },
    ]

    try:
        for strategy in table_strategies:
            try:
                raw_tables = page.extract_tables(table_settings=strategy) if strategy else page.extract_tables()
            except Exception:
                continue
            if not raw_tables:
                continue
            strategy_label = "pdfplumber default"
            if strategy:
                strategy_label = (
                    f"pdfplumber (v:{strategy.get('vertical_strategy')}, h:{strategy.get('horizontal_strategy')})"
                )
            for raw_table in raw_tables:
                table_rows: list[list[str]] = []
                for raw_row in (raw_table or []):
                    if not isinstance(raw_row, (list, tuple)):
                        continue
                    table_rows.append([_safe_table_cell(cell) for cell in raw_row])
                if not table_rows:
                    continue
                signature = tuple(tuple(cell for cell in row) for row in table_rows)
                if signature in seen_tables:
                    continue
                markdown = _markdown_table(table_rows)
                if not markdown:
                    continue
                seen_tables.add(signature)
                table_counter += 1
                heading = (
                    f"[TABLE {table_counter}] extracted from page {page_number} using {strategy_label}. "
                    "Cell values and structure were inferred from ruling lines where present."
                )
                passages.extend(
                    chunk_text(f"{heading}\n\n{markdown}", page_number, section="table")
                )
    except Exception:
        return passages
    return passages


def _extract_pdf_figure_notes_with_fitz(page: Any, page_number: int) -> list[dict[str, Any]]:
    try:
        images = page.get_images(full=True)
    except Exception:
        return []
    image_count = len(images)
    if image_count <= 0:
        return []
    page_objects: list[dict[str, Any]] = []
    for image in images:
        if not isinstance(image, tuple) or len(image) < 4:
            continue
        xref = image[0]
        width = float(image[2]) if isinstance(image[2], (int, float)) else 0.0
        height = float(image[3]) if isinstance(image[3], (int, float)) else 0.0
        bbox = None
        if isinstance(xref, int):
            try:
                rect = page.get_image_bbox(xref)
                if rect:
                    bbox = [round(float(value), 2) for value in (rect.x0, rect.y0, rect.x1, rect.y1)]
            except Exception:
                bbox = None
        page_objects.append(
            {
                "xref": xref,
                "width": width,
                "height": height,
                "area": width * height,
                "bbox": bbox,
            }
        )
    page_objects.sort(key=lambda item: item.get("area", 0.0), reverse=True)
    top_objects = page_objects[:3]
    notable_objects: list[str] = []
    for item in top_objects:
        if item.get("width") and item.get("height"):
            bbox = item.get("bbox")
            bbox_text = (
                f", bbox={bbox[0]:.0f},{bbox[1]:.0f},{bbox[2]:.0f},{bbox[3]:.0f}"
                if bbox else ""
            )
            notable_objects.append(
                f"{item['width']:.0f}x{item['height']:.0f}px (area {item['area']:,.0f} px²){bbox_text}"
            )
    note = (
        f"[FIGURE cues] page {page_number} contains {image_count} embedded figure or image object(s). "
        "For visual interpretation, check the original PDF where needed."
    )
    if notable_objects:
        note += " Largest objects: " + "; ".join(notable_objects)
    captions: list[str] = []
    try:
        page_text = (page.get_text() or "").splitlines()
        caption_pattern = re.compile(r"\b(?:figure|fig\.)\s*\d+", re.IGNORECASE)
        for index, line in enumerate(page_text):
            if caption_pattern.search(line):
                neighborhood = [
                    page_text[index - 1] if index > 0 else "",
                    line,
                    page_text[index + 1] if index + 1 < len(page_text) else "",
                ]
                phrase = " ".join(part.strip() for part in neighborhood if part and part.strip())
                if phrase:
                    captions.append(re.sub(r"\s+", " ", phrase).strip())
    except Exception:
        captions = []
    if captions:
        seen: list[str] = []
        for candidate in captions:
            if candidate not in seen:
                seen.append(candidate)
            if len(seen) >= 2:
                break
        note += " Caption hints: " + "; ".join(seen)
    return [{"page_number": page_number, "section": "figure_note", "content": note}]


def _extract_pdf_tables_with_fitz(
    page: Any,
    page_number: int,
    seen_tables: set[tuple[tuple[str, ...], ...]] | None = None,
) -> list[dict[str, Any]]:
    if seen_tables is None:
        seen_tables = set()
    passages: list[dict[str, Any]] = []
    try:
        for table_index, table in enumerate(page.find_tables(), start=1):
            raw_table = table.extract() or []
            if not raw_table:
                continue
            rows: list[list[str]] = []
            for raw_row in raw_table:
                if not isinstance(raw_row, (list, tuple)):
                    continue
                rows.append([_safe_table_cell(cell) for cell in raw_row])
            if not rows:
                continue
            signature = tuple(tuple(cell for cell in row) for row in rows)
            if signature in seen_tables:
                continue
            markdown = _markdown_table(rows)
            if not markdown:
                continue
            seen_tables.add(signature)
            heading = f"[TABLE {table_index}] extracted from page {page_number} using PyMuPDF."
            passages.extend(chunk_text(f"{heading}\n\n{markdown}", page_number, section="fitz_table"))
    except Exception:
        pass
    return passages


def _open_fitz():
    fitz_module = None
    if _has_module("fitz"):
        try:
            import fitz  # type: ignore
            fitz_module = fitz
        except Exception:
            fitz_module = None
    elif _has_module("pymupdf"):
        try:
            import pymupdf as fitz  # type: ignore
            fitz_module = fitz
        except Exception:
            fitz_module = None
    return fitz_module


def _extract_pdf_with_pdfplumber(path: Path) -> list[dict[str, Any]]:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return []

    fitz_module = _open_fitz()
    pdf_with_images = None
    seen_tables: set[tuple[tuple[str, ...], ...]] = set()
    passages: list[dict[str, Any]] = []
    try:
        if fitz_module is not None:
            pdf_with_images = fitz_module.open(str(path))

        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    page_text = (page.extract_text() or "").strip()
                    if page_text:
                        passages.extend(
                            chunk_text(
                                f"[PAGE {page_number} TEXT]\n{page_text}",
                                page_number,
                                section="text",
                            )
                        )
                    passages.extend(
                        _extract_pdf_tables_with_pdfplumber(page, page_number, seen_tables)
                    )
                    if pdf_with_images is not None:
                        try:
                            fitz_page = pdf_with_images.load_page(page_number - 1)
                            passages.extend(_extract_pdf_figure_notes_with_fitz(fitz_page, page_number))
                            passages.extend(
                                _extract_pdf_tables_with_fitz(
                                    fitz_page, page_number, seen_tables
                                )
                            )
                        except Exception:
                            pass
                except Exception:
                    continue
    finally:
        if pdf_with_images is not None:
            try:
                pdf_with_images.close()
            except Exception:
                pass
    return passages


def _extract_pdf_with_fitz(path: Path) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    fitz_module = _open_fitz()
    if fitz_module is None:
        return passages
    try:
        doc = fitz_module.open(str(path))
    except Exception:
        return passages
    try:
        for page_number in range(doc.page_count):
            page = doc.load_page(page_number)
            text = (page.get_text("text") or "").strip()
            if text:
                passages.extend(
                    chunk_text(
                        f"[PAGE {page_number + 1} TEXT]\n{text}",
                        page_number + 1,
                        section="text",
                    )
                )
            passages.extend(_extract_pdf_tables_with_fitz(page, page_number + 1))
            passages.extend(_extract_pdf_figure_notes_with_fitz(page, page_number + 1))
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return passages


def _extract_pdf_with_pypdf(path: Path) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return []
    passages: list[dict[str, Any]] = []
    reader = PdfReader(str(path))
    for page_index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            passages.extend(
                chunk_text(f"[PAGE {page_index} TEXT]\n{text}", page_index, section="text")
            )
    return passages


def _extract_passages_pdf(path: Path) -> list[dict[str, Any]]:
    passages = _extract_pdf_with_pdfplumber(path)
    if passages:
        return passages
    passages = _extract_pdf_with_fitz(path)
    if passages:
        return passages
    passages = _extract_pdf_with_pypdf(path)
    if passages:
        return passages
    raise RuntimeError(
        "PDF parsing dependencies are not available. Install both PyMuPDF and pdfplumber "
        "for better table extraction and figure detection: pip install pymupdf pdfplumber"
    )


def extract_passages(path: Path) -> list[dict[str, Any]]:
    extension = path.suffix.lower()
    if extension == ".pdf":
        return _extract_passages_pdf(path)
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
        section = passage.get("section")
        section_marker = f" ({section})" if section else ""
        parts.append(f"[{filename}, {locator}{section_marker}]\n{passage['content']}")
    return "\n\n---\n\n".join(parts)

