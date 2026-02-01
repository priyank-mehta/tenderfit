"""Application orchestration for TenderFit."""

from __future__ import annotations

from typing import Any

from tenderfit.agents import TenderFitOrchestrator


def run() -> None:
    """Entry point placeholder for future CLI wiring."""
    raise SystemExit("Use TenderFitOrchestrator via tenderfit.app.evaluate_bid.")


def evaluate_bid(
    *,
    bid_id: str,
    doc_urls: list[str],
    company_profile_path: str,
    model: str = "gpt-4.1-mini",
    cache_dir: str | None = None,
    artifacts_dir: str | None = None,
    reports_dir: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Convenience wrapper for running the full multi-agent evaluation."""

    orchestrator = TenderFitOrchestrator(model=model, cache_dir=cache_dir)
    report, report_md = orchestrator.evaluate_bid(
        bid_id=bid_id,
        doc_urls=doc_urls,
        company_profile_path=company_profile_path,
        artifacts_dir=artifacts_dir,
        reports_dir=reports_dir,
    )
    return report.model_dump(by_alias=True), report_md
