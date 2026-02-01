"""BidPlus scouting tool for live bid discovery via agent-browser."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from pathlib import Path
import subprocess
from typing import Any
import uuid

from pydantic import BaseModel
from openai import OpenAI

from tenderfit.tools.cache import ToolCache


BIDPLUS_ALL_BIDS_URL = "https://bidplus.gem.gov.in/all-bids"
BIDPLUS_ALL_BIDS_DATA_URL = "https://bidplus.gem.gov.in/all-bids-data"


class BidPlusBid(BaseModel):
    bid_id: str
    title: str
    url: str | None = None
    closing_date: str | None = None
    summary: str | None = None
    score: float | None = None
    raw: dict[str, Any] | None = None


class BidPlusScoutInput(BaseModel):
    keywords: str
    days: int = 14
    top_n: int = 30
    max_pages: int = 5
    cache_dir: str | None = None
    use_server_search: bool = True
    write_data_path: str | None = None
    llm_filter: bool = False
    llm_model: str = "gpt-4.1-mini"
    llm_max_candidates: int = 100
    llm_batch_size: int = 5
    force_refresh: bool = False


class BidPlusScoutOutput(BaseModel):
    bids: list[BidPlusBid]
    cached: bool = False
    total: int
    query: str
    notes: str | None = None


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


def _extract_csrf(html: str) -> str | None:
    match = re.search(r"csrf_bd_gem_nk\s*'?:\s*'([a-f0-9]+)'", html)
    if match:
        return match.group(1)
    return None


def _first_value(value: Any) -> str | None:
    if isinstance(value, list):
        return value[0] if value else None
    if value is None:
        return None
    return str(value)


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_bid_url(bid_type: int | None, eval_type: int | None, bid_internal_id: str) -> str:
    doc_label = "showbidDocument"
    if bid_type == 5:
        doc_label = "showdirectradocumentPdf"
    elif bid_type == 2:
        doc_label = "showradocumentPdf"
        if eval_type and eval_type > 0:
            doc_label = "list-ra-schedules"
    return f"https://bidplus.gem.gov.in/{doc_label}/{bid_internal_id}"


def _score_bid(bid: dict[str, Any], tokens: list[str]) -> float:
    haystack = " ".join(
        str(bid.get(field, "")) for field in ("title", "summary", "bid_id", "ministry", "department")
    ).lower()
    return float(sum(1 for token in tokens if token in haystack))


def _normalize_bid(doc: dict[str, Any]) -> dict[str, Any]:
    bid_internal_id = _first_value(doc.get("b_id")) or ""
    bid_number = _first_value(doc.get("b_bid_number")) or bid_internal_id
    title = (
        _first_value(doc.get("bd_category_name"))
        or _first_value(doc.get("b_category_name"))
        or bid_number
    )
    ministry = _first_value(doc.get("ba_official_details_minName"))
    department = _first_value(doc.get("ba_official_details_deptName"))
    summary_parts = [part for part in (ministry, department) if part]
    summary = " | ".join(summary_parts) if summary_parts else None

    bid_type = None
    eval_type = None
    try:
        bid_type = int(_first_value(doc.get("b_bid_type") or doc.get("b_bid_type")))
    except (TypeError, ValueError):
        bid_type = None
    try:
        eval_type = int(_first_value(doc.get("b_eval_type") or doc.get("b_eval_type")))
    except (TypeError, ValueError):
        eval_type = None

    closing_date = _first_value(doc.get("final_end_date_sort"))
    url = _build_bid_url(bid_type, eval_type, bid_internal_id) if bid_internal_id else None
    return {
        "bid_id": bid_number,
        "title": title,
        "url": url,
        "closing_date": closing_date,
        "summary": summary,
        "ministry": ministry,
        "department": department,
        "raw": doc,
    }


def _parse_eval_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith('"'):
        return json.loads(text)
    return text


def _parse_eval_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise RuntimeError("agent-browser eval returned empty response.")
    if text.startswith('"'):
        text = json.loads(text)
    return json.loads(text)


def _hash_payload(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _extract_json_payload(text: str) -> Any:
    trimmed = text.strip()
    if trimmed.startswith("{") or trimmed.startswith("["):
        return json.loads(trimmed)
    match = re.search(r"\[.*\]|\{.*\}", text, re.S)
    if not match:
        raise ValueError("No JSON payload found in LLM response.")
    return json.loads(match.group(0))


def _llm_filter_bids(
    bids: list[dict[str, Any]],
    *,
    model: str,
    cache: ToolCache,
    batch_size: int,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], str | None]:
    client = OpenAI()
    filtered: list[dict[str, Any]] = []
    notes: list[str] = []

    system_prompt = (
        "You are a strict classifier. Determine if a bid is for cab/taxi/vehicle hiring "
        "services (including monthly/short-term cab taxi hiring). Respond in JSON only: "
        "{\"relevant\": true/false, \"reason\": \"short\"}."
    )

    candidates = bids
    if max_candidates > 0 and len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]
        notes.append(f"llm_max_candidates={max_candidates}")

    cached_map: dict[str, bool] = {}
    uncached: list[dict[str, Any]] = []
    for bid in candidates:
        payload = bid.get("raw") or bid
        cache_key = {
            "bid_id": bid.get("bid_id"),
            "model": model,
            "payload_hash": _hash_payload(payload),
        }
        cached = cache.get("bidplus_llm_filter", cache_key)
        if cached is None:
            uncached.append(bid)
            continue
        cached_map[str(bid.get("bid_id"))] = bool(cached.get("relevant"))
        if cached.get("relevant"):
            filtered.append(bid)

    for start in range(0, len(uncached), max(batch_size, 1)):
        batch = uncached[start : start + max(batch_size, 1)]
        payloads = []
        for bid in batch:
            payloads.append(
                {
                    "bid_id": bid.get("bid_id"),
                    "payload": bid.get("raw") or bid,
                }
            )
        user_prompt = (
            "Classify each bid as cab/taxi/vehicle hiring related. Respond JSON array only: "
            "[{\"bid_id\": \"...\", \"relevant\": true/false, \"reason\": \"short\"}].\n\n"
            f"Bids:\n{json.dumps(payloads, ensure_ascii=True, indent=2)}"
        )
        response = client.responses.create(
            model=model,
            temperature=0,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.output_text or ""
        parsed = _extract_json_payload(content)
        if not isinstance(parsed, list):
            raise ValueError("LLM response did not return a JSON array.")
        for item in parsed:
            bid_id = str(item.get("bid_id"))
            relevant = bool(item.get("relevant"))
            cache_key = {
                "bid_id": bid_id,
                "model": model,
                "payload_hash": _hash_payload(
                    next(
                        (b.get("raw") or b for b in batch if str(b.get("bid_id")) == bid_id),
                        {"bid_id": bid_id},
                    )
                ),
            }
            cache.set(
                "bidplus_llm_filter",
                cache_key,
                {"relevant": relevant, "reason": item.get("reason")},
            )
            cached_map[bid_id] = relevant

        for bid in batch:
            if cached_map.get(str(bid.get("bid_id"))):
                filtered.append(bid)

    return filtered, "; ".join(notes) if notes else None


def bidplus_scout(
    *,
    keywords: str,
    days: int = 14,
    top_n: int = 30,
    max_pages: int = 5,
    cache_dir: str | None = None,
    use_server_search: bool = True,
    write_data_path: str | None = None,
    llm_filter: bool = False,
    llm_model: str = "gpt-4.1-mini",
    llm_max_candidates: int = 100,
    llm_batch_size: int = 5,
    force_refresh: bool = False,
) -> BidPlusScoutOutput:
    """Query BidPlus All Bids endpoint via agent-browser and return matching bids."""

    inputs = BidPlusScoutInput(
        keywords=keywords,
        days=days,
        top_n=top_n,
        max_pages=max_pages,
        cache_dir=cache_dir,
        use_server_search=use_server_search,
        write_data_path=write_data_path,
        llm_filter=llm_filter,
        llm_model=llm_model,
        llm_max_candidates=llm_max_candidates,
        llm_batch_size=llm_batch_size,
        force_refresh=force_refresh,
    )
    cache = ToolCache(inputs.cache_dir)
    cache_key = inputs.model_dump(exclude={"write_data_path"})

    if not inputs.force_refresh:
        cached = cache.get("bidplus_scout", cache_key)
        if cached is not None:
            cached["cached"] = True
            return BidPlusScoutOutput.model_validate(cached)

    session = f"tenderfit-scout-{uuid.uuid4().hex[:8]}"
    _run_agent_browser(session, "open", BIDPLUS_ALL_BIDS_URL)
    html_raw = _run_agent_browser(session, "eval", "document.documentElement.innerHTML")
    html = _parse_eval_text(html_raw)
    csrf = _extract_csrf(html) if html else None
    if not csrf:
        _run_agent_browser(session, "close")
        raise RuntimeError("BidPlus CSRF token not found; page layout may have changed.")

    stopwords = {
        "and",
        "or",
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "in",
        "on",
        "with",
        "by",
        "from",
    }
    tokens = [
        token.lower()
        for token in keywords.split()
        if token.strip() and token.lower() not in stopwords
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    notes: list[str] = []

    base_filter = {
        "bidStatusType": "ongoing_bids",
        "byType": "all",
        "highBidValue": "",
        "byEndDate": {"from": "", "to": ""},
        "sort": "Bid-End-Date-Oldest",
    }

    def fetch_page(page: int, search_term: str) -> dict[str, Any]:
        payload = {
            "param": {"searchBid": search_term, "searchType": "fullText"},
            "filter": base_filter,
            "page": page,
        }
        script = (
            "(async () => {"
            f"const csrf = {json.dumps(csrf)};"
            f"const payload = {json.dumps(payload)};"
            "const body = new URLSearchParams({payload: JSON.stringify(payload), csrf_bd_gem_nk: csrf});"
            f"const resp = await fetch({json.dumps(BIDPLUS_ALL_BIDS_DATA_URL)}, {{"
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
        return _parse_eval_json(raw)

    results: list[dict[str, Any]] = []
    total_found = 0
    fetched_pages = 0
    search_terms: list[str] = []
    if use_server_search:
        search_terms = [
            token.strip()
            for token in keywords.split()
            if token.strip() and token.lower() not in stopwords
        ]
        if not search_terms:
            search_terms = [keywords.strip()] if keywords.strip() else []
    if not search_terms:
        search_terms = [""]
    server_used = False

    try:
        if len(search_terms) > 1 and use_server_search:
            seen: dict[str, dict[str, Any]] = {}
            for term in search_terms:
                for page in range(1, max_pages + 1):
                    payload_response = fetch_page(page, term)
                    fetched_pages += 1
                    if payload_response.get("status") == 0 and payload_response.get("code") == 404:
                        break
                    response = (
                        payload_response.get("response", {})
                        .get("response", {})
                    )
                    docs = response.get("docs", [])
                    if not docs:
                        break
                    server_used = True
                    total_found = response.get("numFound", total_found)
                    for doc in docs:
                        bid = _normalize_bid(doc)
                        bid_id = bid.get("bid_id")
                        if bid_id:
                            seen[bid_id] = bid
                        else:
                            results.append(bid)
            results.extend(seen.values())
            notes.append(f"token_search={len(search_terms)}")
        else:
            search_term = search_terms[0]
            for page in range(1, max_pages + 1):
                payload_response = fetch_page(page, search_term)
                fetched_pages += 1
                if payload_response.get("status") == 0 and payload_response.get("code") == 404:
                    break
                response = (
                    payload_response.get("response", {})
                    .get("response", {})
                )
                docs = response.get("docs", [])
                if not docs:
                    break
                server_used = True
                total_found = response.get("numFound", total_found)
                for doc in docs:
                    results.append(_normalize_bid(doc))

        if not results and tokens:
            notes.append("server search returned no data; falling back to local filter")
            total_found = 0
            for page in range(1, max_pages + 1):
                payload_response = fetch_page(page, "")
                fetched_pages += 1
                response = (
                    payload_response.get("response", {})
                    .get("response", {})
                )
                docs = response.get("docs", [])
                if not docs:
                    break
                total_found = response.get("numFound", total_found)
                for doc in docs:
                    results.append(_normalize_bid(doc))
    finally:
        _run_agent_browser(session, "close")

    filtered: list[dict[str, Any]] = []
    for bid in results:
        closing_date = _parse_iso_date(bid.get("closing_date"))
        if closing_date and closing_date < cutoff:
            continue
        score = _score_bid(bid, tokens) if tokens else 0.0
        if tokens and score == 0:
            continue
        bid["score"] = score
        filtered.append(bid)

    filtered.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    if llm_filter:
        filtered, llm_notes = _llm_filter_bids(
            filtered,
            model=llm_model,
            cache=cache,
            batch_size=llm_batch_size,
            max_candidates=llm_max_candidates,
        )
        if llm_notes:
            notes.append(llm_notes)
    selected = filtered[:top_n]
    output = BidPlusScoutOutput(
        bids=[BidPlusBid.model_validate(item) for item in selected],
        cached=False,
        total=len(filtered) if filtered else total_found,
        query=keywords,
        notes="; ".join(
            [
                f"pages_fetched={fetched_pages}",
                f"server_search={server_used}",
                *notes,
            ]
        ),
    )

    if inputs.write_data_path:
        path = Path(inputs.write_data_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([bid.model_dump() for bid in output.bids], indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    if not inputs.force_refresh:
        cache.set("bidplus_scout", cache_key, output.model_dump())
    return output
