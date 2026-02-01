"""Eval harness for TenderFit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUITES = {
    "quick": "quick.jsonl",
    "scout": "scout.jsonl",
    "collector": "collector.jsonl",
    "extractor": "extractor.jsonl",
    "verifier": "verifier.jsonl",
    "arbiter": "arbiter.jsonl",
    "shortlist": "shortlist.jsonl",
}


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    coverage: float
    covered_count: int
    total_requirements: int
    uncited_requirements: list[str]
    quote_errors: list[str]
    corrigendum_errors: list[str]
    passed: bool


def load_suite(name: str) -> list[dict[str, Any]]:
    suite_file = SUITES.get(name)
    if not suite_file:
        raise ValueError(f"Unknown eval suite: {name}")
    path = Path(__file__).resolve().parent / suite_file
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cases.append(json.loads(line))
    return cases


def evaluate_case(case: dict[str, Any]) -> CaseResult:
    requirements = case.get("requirements", [])
    output = case.get("output", {})
    resolved = {item["requirement_id"]: item for item in output.get("resolved_requirements", [])}

    chunk_lookup = {
        chunk["chunk_id"]: chunk.get("text", "") for chunk in case.get("chunks", [])
    }

    covered = 0
    uncited: list[str] = []
    quote_errors: list[str] = []
    for requirement in requirements:
        req_id = requirement.get("requirement_id", "")
        output_req = resolved.get(req_id)
        citations = output_req.get("citations") if output_req else None
        if citations:
            covered += 1
        else:
            uncited.append(req_id)
        for citation in citations or []:
            chunk_id = citation.get("chunk_id")
            quote = citation.get("quote", "")
            chunk_text = chunk_lookup.get(chunk_id, "")
            if not quote or quote not in chunk_text:
                quote_errors.append(f"{req_id}:{chunk_id}")

    total = len(requirements)
    coverage = covered / total if total else 1.0

    corrigendum_errors: list[str] = []
    for update in case.get("corrigendum", []):
        req_id = update.get("requirement_id", "")
        expected_text = update.get("text", "")
        output_req = resolved.get(req_id)
        output_text = output_req.get("text", "") if output_req else ""
        if expected_text and output_text != expected_text:
            corrigendum_errors.append(req_id)

    passed = not quote_errors and not corrigendum_errors
    return CaseResult(
        case_id=case.get("id", "unknown"),
        coverage=coverage,
        covered_count=covered,
        total_requirements=total,
        uncited_requirements=uncited,
        quote_errors=quote_errors,
        corrigendum_errors=corrigendum_errors,
        passed=passed,
    )


def run_suite(name: str, *, min_coverage: float = 0.9) -> dict[str, Any]:
    cases = load_suite(name)
    case_results = [evaluate_case(case) for case in cases]
    total_requirements = 0
    total_covered = 0
    for result in case_results:
        total_requirements += result.total_requirements
        total_covered += result.covered_count

    overall_coverage = (
        total_covered / total_requirements if total_requirements else 1.0
    )
    passed = overall_coverage >= min_coverage and all(
        result.passed for result in case_results
    )

    return {
        "suite": name,
        "min_coverage": min_coverage,
        "overall_coverage": overall_coverage,
        "passed": passed,
        "cases": case_results,
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        f"Suite: {result['suite']}",
        f"Coverage: {result['overall_coverage']:.2f} (min {result['min_coverage']:.2f})",
        f"Passed: {result['passed']}",
        "",
    ]
    for case in result["cases"]:
        status = "PASS" if case.passed else "FAIL"
        lines.append(f"{case.case_id}: {status} (coverage {case.coverage:.2f})")
        if case.uncited_requirements:
            lines.append(f"  uncited: {', '.join(case.uncited_requirements)}")
        if case.quote_errors:
            lines.append(f"  quote_errors: {', '.join(case.quote_errors)}")
        if case.corrigendum_errors:
            lines.append(
                f"  corrigendum_errors: {', '.join(case.corrigendum_errors)}"
            )
    return "\n".join(lines)


def run_cli(suite: str, *, min_coverage: float = 0.9) -> int:
    result = run_suite(suite, min_coverage=min_coverage)
    print(format_report(result))
    return 0 if result["passed"] else 1
