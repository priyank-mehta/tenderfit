"""Parse PDF pages into text content."""

from __future__ import annotations

from pydantic import BaseModel

from tenderfit.tools.cache import ToolCache


class ParsePdfInput(BaseModel):
    pdf_path: str
    max_pages: int | None = None
    cache_dir: str | None = None


class PdfPage(BaseModel):
    page_num: int
    text: str


class ParsePdfOutput(BaseModel):
    pages: list[PdfPage]
    cached: bool = False


def _get_reader() -> "PdfReader":
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pypdf is required for parse_pdf.") from exc
    return PdfReader


def parse_pdf(
    *,
    pdf_path: str,
    max_pages: int | None = None,
    cache_dir: str | None = None,
) -> ParsePdfOutput:
    """Extract page text from a PDF using pypdf."""

    inputs = ParsePdfInput(
        pdf_path=pdf_path, max_pages=max_pages, cache_dir=cache_dir
    )
    cache = ToolCache(inputs.cache_dir)
    cache_key = inputs.model_dump()

    cached = cache.get("parse_pdf", cache_key)
    if cached is not None:
        cached["cached"] = True
        return ParsePdfOutput.model_validate(cached)

    reader_cls = _get_reader()
    reader = reader_cls(inputs.pdf_path)
    total_pages = len(reader.pages)
    limit = min(inputs.max_pages, total_pages) if inputs.max_pages else total_pages

    pages: list[PdfPage] = []
    for index in range(limit):
        page = reader.pages[index]
        text = page.extract_text() or ""
        pages.append(PdfPage(page_num=index + 1, text=text))

    output = ParsePdfOutput(pages=pages, cached=False)
    cache.set("parse_pdf", cache_key, output.model_dump())
    return output
