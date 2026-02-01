"""Search tender listings (local cache-backed)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tenderfit.tools.cache import ToolCache


class Bid(BaseModel):
    bid_id: str
    title: str
    url: str | None = None
    published_at: str | None = None
    summary: str | None = None
    score: float | None = None


class SearchBidsInput(BaseModel):
    keyword: str
    days: int = 14
    top_n: int = 30
    data_path: str | None = None
    cache_dir: str | None = None


class SearchBidsOutput(BaseModel):
    bids: list[Bid]
    cached: bool = False
    total: int
    query: str


def _load_bids(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return rows
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _score_bid(bid: dict[str, Any], tokens: list[str]) -> float:
    haystack = " ".join(
        str(bid.get(field, "")) for field in ("title", "summary", "keywords")
    ).lower()
    return float(sum(1 for token in tokens if token in haystack))


def search_bids(
    *,
    keyword: str,
    days: int = 14,
    top_n: int = 30,
    data_path: str | None = None,
    cache_dir: str | None = None,
) -> SearchBidsOutput:
    """Search locally cached bid listings with a simple keyword filter."""

    inputs = SearchBidsInput(
        keyword=keyword, days=days, top_n=top_n, data_path=data_path, cache_dir=cache_dir
    )
    cache = ToolCache(inputs.cache_dir)
    cache_key = inputs.model_dump()

    cached = cache.get("search_bids", cache_key)
    if cached is not None:
        cached["cached"] = True
        return SearchBidsOutput.model_validate(cached)

    data_file = Path(inputs.data_path) if inputs.data_path else Path("artifacts/bids.json")
    bids = _load_bids(data_file)
    tokens = [token.lower() for token in inputs.keyword.split() if token.strip()]
    cutoff = datetime.now(timezone.utc) - timedelta(days=inputs.days)

    filtered: list[dict[str, Any]] = []
    for bid in bids:
        score = _score_bid(bid, tokens) if tokens else 0.0
        if tokens and score == 0:
            continue
        published_at = _parse_date(bid.get("published_at"))
        if published_at and published_at < cutoff:
            continue
        bid = dict(bid)
        bid["score"] = score
        filtered.append(bid)

    filtered.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    selected = filtered[: inputs.top_n]
    output = SearchBidsOutput(
        bids=[Bid.model_validate(item) for item in selected],
        cached=False,
        total=len(filtered),
        query=inputs.keyword,
    )
    cache.set("search_bids", cache_key, output.model_dump())
    return output
