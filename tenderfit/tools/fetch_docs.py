"""Fetch bid documents with basic caching."""

from __future__ import annotations

from pathlib import Path
import shutil
from urllib.parse import urlparse
from urllib.request import urlretrieve

from pydantic import BaseModel, Field

from tenderfit.tools.cache import ToolCache


class FetchDocsInput(BaseModel):
    bid_id: str
    doc_urls: list[str] = Field(default_factory=list)
    out_dir: str
    cache_dir: str | None = None


class FetchDocsOutput(BaseModel):
    downloaded: list[str]
    skipped: list[str]
    errors: list[str]
    cached: bool = False


def _copy_local(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _fetch_one(url: str, out_dir: Path) -> tuple[str | None, str | None]:
    parsed = urlparse(url)
    if parsed.scheme in ("", "file"):
        src_path = Path(parsed.path if parsed.scheme == "file" else url)
        if not src_path.exists():
            return None, f"Missing source: {url}"
        dest = out_dir / src_path.name
        if dest.exists():
            return str(dest), None
        _copy_local(src_path, dest)
        return str(dest), None

    if parsed.scheme in ("http", "https"):
        filename = Path(parsed.path).name or "document.pdf"
        dest = out_dir / filename
        if dest.exists():
            return str(dest), None
        dest.parent.mkdir(parents=True, exist_ok=True)
        urlretrieve(url, dest)
        return str(dest), None

    return None, f"Unsupported URL scheme: {url}"


def fetch_docs(
    *,
    bid_id: str,
    doc_urls: list[str],
    out_dir: str,
    cache_dir: str | None = None,
) -> FetchDocsOutput:
    """Download bid documents into the requested folder."""

    inputs = FetchDocsInput(
        bid_id=bid_id, doc_urls=doc_urls, out_dir=out_dir, cache_dir=cache_dir
    )
    cache = ToolCache(inputs.cache_dir)
    cache_key = inputs.model_dump()

    cached = cache.get("fetch_docs", cache_key)
    if cached is not None:
        cached_paths = cached.get("downloaded", [])
        if all(Path(path).exists() for path in cached_paths):
            cached["cached"] = True
            return FetchDocsOutput.model_validate(cached)

    out_path = Path(inputs.out_dir)
    downloaded: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    if not inputs.doc_urls:
        errors.append("No document URLs supplied.")

    for url in inputs.doc_urls:
        dest, error = _fetch_one(url, out_path)
        if error:
            errors.append(error)
            continue
        if dest and Path(dest).exists():
            if dest in downloaded:
                skipped.append(dest)
            else:
                downloaded.append(dest)

    output = FetchDocsOutput(
        downloaded=downloaded,
        skipped=skipped,
        errors=errors,
        cached=False,
    )
    cache.set("fetch_docs", cache_key, output.model_dump())
    return output
