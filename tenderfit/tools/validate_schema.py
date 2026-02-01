"""Validate data against a JSON schema."""

from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel

from tenderfit.tools.cache import ToolCache


class ValidateSchemaInput(BaseModel):
    schema_path: str
    data: dict
    cache_dir: str | None = None


class ValidateSchemaOutput(BaseModel):
    valid: bool
    errors: list[str]
    cached: bool = False


def _get_validator(schema: dict, base_uri: str | None) -> "Draft202012Validator":
    try:
        from jsonschema import Draft202012Validator, RefResolver  # type: ignore
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for validate_schema.") from exc
    if base_uri:
        resolver = RefResolver(base_uri=base_uri, referrer=schema)
        return Draft202012Validator(schema, resolver=resolver)
    return Draft202012Validator(schema)


def validate_schema(
    *,
    schema_path: str,
    data: dict,
    cache_dir: str | None = None,
) -> ValidateSchemaOutput:
    """Validate the provided data against a JSON schema file."""

    inputs = ValidateSchemaInput(
        schema_path=schema_path, data=data, cache_dir=cache_dir
    )
    cache = ToolCache(inputs.cache_dir)
    cache_key = inputs.model_dump()

    cached = cache.get("validate_schema", cache_key)
    if cached is not None:
        cached["cached"] = True
        return ValidateSchemaOutput.model_validate(cached)

    schema_file = Path(inputs.schema_path)
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    base_uri = schema_file.resolve().as_uri()
    validator = _get_validator(schema, base_uri)

    errors = []
    for error in sorted(validator.iter_errors(inputs.data), key=lambda err: err.path):
        location = "/".join(str(part) for part in error.path)
        prefix = f"{location}: " if location else ""
        errors.append(f"{prefix}{error.message}")

    output = ValidateSchemaOutput(valid=not errors, errors=errors, cached=False)
    cache.set("validate_schema", cache_key, output.model_dump())
    return output
