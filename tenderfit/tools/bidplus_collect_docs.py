"""Collect bid documents and corrigenda via agent-browser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import json
import re
from pathlib import Path
import subprocess
from typing import Any
import uuid
from urllib.parse import urljoin

from pydantic import BaseModel, Field

from tenderfit.tools.cache import ToolCache


BIDPLUS_BASE_URL = "https://bidplus.gem.gov.in/"
BIDPLUS_ALL_BIDS_URL = "https://bidplus.gem.gov.in/all-bids"


class CollectDocsInput(BaseModel):
    bid_id: str
    listing_path: str
    out_dir: str
    cache_dir: str | None = None


class CollectedDoc(BaseModel):
    doc_id: str
    source_url: str
    local_path: str
    doc_type: str
    title: str | None = None
    fetched_at: str | None = None


class CollectDocsOutput(BaseModel):
    bid_id: str
    documents: list[CollectedDoc]
    errors: list[str] = Field(default_factory=list)
    cached: bool = False


@dataclass(frozen=True)
class FetchResult:
    url: str
    content_type: str | None
    text: str | None
    base64_data: str | None


def _run_agent_browser(session: str, *args: str) -> str:
    command = ["agent-browser", "--session", session, *args]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"agent-browser failed: {' '.join(command)}\n{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _parse_eval_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith('"'):
        return json.loads(text)
    return text


def _fetch_via_browser(session: str, url: str) -> FetchResult:
    script = (
        "(async () => {"
        f"const url = {json.dumps(url)};"
        "const resp = await fetch(url, {method:'GET'});"
        "const contentType = resp.headers.get('content-type') || '';"
        "if (contentType.includes('text/html')) {"
        "  return JSON.stringify({url: resp.url, contentType, text: await resp.text()});"
        "}"
        "const buf = await resp.arrayBuffer();"
        "const bytes = new Uint8Array(buf);"
        "let binary = '';"
        "for (let i = 0; i < bytes.length; i += 0x8000) {"
        "  binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));"
        "}"
        "const base64 = btoa(binary);"
        "return JSON.stringify({url: resp.url, contentType, base64});"
        "})()"
    )
    raw = _run_agent_browser(session, "eval", script)
    text = _parse_eval_text(raw)
    payload = json.loads(text)
    return FetchResult(
        url=payload.get("url", url),
        content_type=payload.get("contentType"),
        text=payload.get("text"),
        base64_data=payload.get("base64"),
    )


def _post_form_via_browser(session: str, url: str, form: dict[str, str]) -> str:
    script = (
        "(async () => {"
        f"const url = {json.dumps(url)};"
        f"const form = {json.dumps(form)};"
        "const body = new URLSearchParams(form);"
        "const resp = await fetch(url, {"
        "method: 'POST',"
        "headers: {"
        "'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',"
        "'X-Requested-With': 'XMLHttpRequest'"
        "},"
        "body"
        "});"
        "return await resp.text();"
        "})()"
    )
    raw = _run_agent_browser(session, "eval", script)
    return _parse_eval_text(raw)


def _extract_links(html: str) -> list[str]:
    links = re.findall(r'href=["\\\']([^"\\\']+)', html, re.I)
    return list(dict.fromkeys(links))


def _classify_doc(url: str, source: str) -> str:
    lower = url.lower()
    if "corrigendum" in lower or "corrigenda" in lower or "viewcorrigendum" in lower:
        return "corrigendum"
    if "atc" in lower:
        return "atc"
    if "sla" in lower:
        return "sla"
    if source == "base":
        return "base"
    return "other"


def collect_docs(
    *,
    bid_id: str,
    listing_path: str,
    out_dir: str,
    cache_dir: str | None = None,
) -> CollectDocsOutput:
    """Download bid docs + corrigenda using agent-browser."""

    inputs = CollectDocsInput(
        bid_id=bid_id,
        listing_path=listing_path,
        out_dir=out_dir,
        cache_dir=cache_dir,
    )
    cache = ToolCache(inputs.cache_dir)
    cache_key = inputs.model_dump()

    cached = cache.get("bidplus_collect_docs", cache_key)
    if cached is not None:
        cached_docs = cached.get("documents", [])
        if all(Path(doc.get("local_path", "")).exists() for doc in cached_docs):
            cached["cached"] = True
            return CollectDocsOutput.model_validate(cached)

    listing = json.loads(Path(inputs.listing_path).read_text(encoding="utf-8"))
    bid = listing.get("bid", {})
    base_url = bid.get("url")
    if not base_url:
        raise RuntimeError("Listing missing bid URL.")

    session = f"tenderfit-collector-{uuid.uuid4().hex[:8]}"
    _run_agent_browser(session, "open", BIDPLUS_ALL_BIDS_URL)
    html = _run_agent_browser(session, "eval", "document.documentElement.innerHTML")
    html = _parse_eval_text(html)
    csrf_match = re.search(r"csrf_bd_gem_nk\\s*'?:\\s*'([a-f0-9]+)'", html)
    csrf = csrf_match.group(1) if csrf_match else ""

    errors: list[str] = []
    documents: list[CollectedDoc] = []
    docs_dir = Path(inputs.out_dir) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    try:
        base_fetch = _fetch_via_browser(session, base_url)
        if base_fetch.base64_data:
            filename = f"base_{bid_id.replace('/', '_')}.pdf"
            dest = docs_dir / filename
            dest.write_bytes(base64.b64decode(base_fetch.base64_data))
            documents.append(
                CollectedDoc(
                    doc_id="DOC-001",
                    source_url=base_fetch.url,
                    local_path=str(dest),
                    doc_type="base",
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        elif base_fetch.text:
            links = _extract_links(base_fetch.text)
            for link in links:
                full_url = urljoin(BIDPLUS_BASE_URL, link)
                if full_url.lower().endswith(".pdf"):
                    doc_fetch = _fetch_via_browser(session, full_url)
                    if not doc_fetch.base64_data:
                        continue
                    filename = Path(full_url).name or f"doc_{len(documents)+1}.pdf"
                    dest = docs_dir / filename
                    dest.write_bytes(base64.b64decode(doc_fetch.base64_data))
                    doc_type = _classify_doc(full_url, "base")
                    documents.append(
                        CollectedDoc(
                            doc_id=f"DOC-{len(documents)+1:03d}",
                            source_url=doc_fetch.url,
                            local_path=str(dest),
                            doc_type=doc_type,
                            fetched_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )

        bid_internal_id = None
        raw = bid.get("raw") or {}
        if isinstance(raw, dict):
            internal = raw.get("b_id")
            if isinstance(internal, list) and internal:
                bid_internal_id = str(internal[0])
            elif internal:
                bid_internal_id = str(internal)
        if not bid_internal_id:
            match = re.search(r"/(\\d+)$", base_url or "")
            if match:
                bid_internal_id = match.group(1)

        if bid_internal_id:
            if csrf:
                details_url = f"{BIDPLUS_BASE_URL}public-bid-other-details/{bid_internal_id}"
                details_text = _post_form_via_browser(session, details_url, {"csrf_bd_gem_nk": csrf})
                try:
                    details = json.loads(details_text)
                except json.JSONDecodeError:
                    details = {}
            else:
                details = {}

            corr_url = f"{BIDPLUS_BASE_URL}bidding/bid/viewCorrigendum/{bid_internal_id}"
            corr_fetch = _fetch_via_browser(session, corr_url)
            corr_text = corr_fetch.text.strip() if corr_fetch.text else ""
            if corr_text not in {"0", ""} or details.get("response", {}).get("corrigendum"):
                links = _extract_links(corr_fetch.text or "")
                for link in links:
                    full_url = urljoin(BIDPLUS_BASE_URL, link)
                    if not full_url.lower().endswith(".pdf"):
                        continue
                    doc_fetch = _fetch_via_browser(session, full_url)
                    if not doc_fetch.base64_data:
                        continue
                    filename = Path(full_url).name or f"corr_{len(documents)+1}.pdf"
                    dest = docs_dir / filename
                    dest.write_bytes(base64.b64decode(doc_fetch.base64_data))
                    documents.append(
                        CollectedDoc(
                            doc_id=f"DOC-{len(documents)+1:03d}",
                            source_url=doc_fetch.url,
                            local_path=str(dest),
                            doc_type="corrigendum",
                            fetched_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )
    except Exception as exc:
        errors.append(str(exc))
    finally:
        _run_agent_browser(session, "close")

    output = CollectDocsOutput(
        bid_id=bid_id,
        documents=documents,
        errors=errors,
        cached=False,
    )
    cache.set("bidplus_collect_docs", cache_key, output.model_dump())
    return output
