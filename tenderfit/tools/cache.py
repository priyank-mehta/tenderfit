"""Shared caching helpers for tool calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ToolCache:
    """Tiny JSON cache keyed by tool name + input payload."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or ".cache/tools")

    def _key_path(self, tool_name: str, key: dict[str, Any]) -> Path:
        key_json = json.dumps(
            key,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(key_json.encode("utf-8")).hexdigest()
        return self.base_dir / tool_name / f"{digest}.json"

    def get(self, tool_name: str, key: dict[str, Any]) -> dict[str, Any] | None:
        path = self._key_path(tool_name, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, tool_name: str, key: dict[str, Any], value: dict[str, Any]) -> Path:
        path = self._key_path(tool_name, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")
        return path
