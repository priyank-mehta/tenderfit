"""Chunk page-level text into overlapping spans."""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel

from tenderfit.tools.cache import ToolCache


class PageText(BaseModel):
    page_num: int
    text: str


class ChunkTextInput(BaseModel):
    pages: list[PageText]
    chunk_size: int = 800
    overlap: int = 100
    cache_dir: str | None = None


class TextChunk(BaseModel):
    chunk_id: str
    chunk_index: int
    page_start: int
    page_end: int
    text: str


class ChunkTextOutput(BaseModel):
    chunks: list[TextChunk]
    cached: bool = False


def _chunk_string(text: str, chunk_size: int, overlap: int) -> Iterable[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        yield text[start:end]
        if end == length:
            break
        start = end - overlap


def chunk_text(
    *,
    pages: list[PageText] | list[dict],
    chunk_size: int = 800,
    overlap: int = 100,
    cache_dir: str | None = None,
) -> ChunkTextOutput:
    """Split page text into fixed-size overlapping chunks."""

    normalized_pages = [PageText.model_validate(page) for page in pages]
    inputs = ChunkTextInput(
        pages=normalized_pages,
        chunk_size=chunk_size,
        overlap=overlap,
        cache_dir=cache_dir,
    )
    cache = ToolCache(inputs.cache_dir)
    cache_key = inputs.model_dump()

    cached = cache.get("chunk_text", cache_key)
    if cached is not None:
        cached["cached"] = True
        return ChunkTextOutput.model_validate(cached)

    chunks: list[TextChunk] = []
    chunk_index = 0
    for page in inputs.pages:
        for local_index, piece in enumerate(
            _chunk_string(page.text, inputs.chunk_size, inputs.overlap)
        ):
            chunk_id = f"p{page.page_num}-c{local_index + 1}"
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    chunk_index=chunk_index,
                    page_start=page.page_num,
                    page_end=page.page_num,
                    text=piece,
                )
            )
            chunk_index += 1

    output = ChunkTextOutput(chunks=chunks, cached=False)
    cache.set("chunk_text", cache_key, output.model_dump())
    return output
