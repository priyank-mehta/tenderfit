"""Agents SDK-style orchestrator for TenderFit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import structlog
from openai import OpenAI

from tenderfit.agents.models import (
    CompanyProfile,
    EvidenceManifest,
    ScoutResults,
    TenderFitReport,
    TenderRequirements,
    VerifierReport,
)
from tenderfit.agents.prompts import (
    ARBITER_SYSTEM_PROMPT,
    COLLECTOR_SYSTEM_PROMPT,
    EXTRACTOR_SYSTEM_PROMPT,
    SCOUT_SYSTEM_PROMPT,
    VERIFIER_SYSTEM_PROMPT,
)
from tenderfit.tools.chunk_text import chunk_text
from tenderfit.tools.fetch_docs import fetch_docs
from tenderfit.tools.parse_pdf import parse_pdf
from tenderfit.tools.search_bids import search_bids
from tenderfit.tools.validate_schema import validate_schema


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = PROJECT_ROOT / "schemas"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    system_prompt: str
    schema_path: Path


class TenderFitOrchestrator:
    """Coordinate the Scout -> Collector -> Extractor -> Verifiers -> Arbiter flow."""

    def __init__(
        self,
        *,
        model: str = "gpt-4.1-mini",
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        cache_dir: str | None = None,
    ) -> None:
        self.client = OpenAI()
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.cache_dir = cache_dir
        self.logger = structlog.get_logger(__name__)

        self._scout = AgentSpec(
            name="ScoutAgent",
            system_prompt=SCOUT_SYSTEM_PROMPT,
            schema_path=SCHEMAS_DIR / "scout_results.schema.json",
        )
        self._collector = AgentSpec(
            name="CollectorAgent",
            system_prompt=COLLECTOR_SYSTEM_PROMPT,
            schema_path=SCHEMAS_DIR / "evidence_manifest.schema.json",
        )
        self._extractor = AgentSpec(
            name="ExtractorAgent",
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
            schema_path=SCHEMAS_DIR / "tender_requirements.schema.json",
        )
        self._verifier = AgentSpec(
            name="VerifierAgent",
            system_prompt=VERIFIER_SYSTEM_PROMPT,
            schema_path=SCHEMAS_DIR / "verifier_report.schema.json",
        )
        self._arbiter = AgentSpec(
            name="ArbiterScorerAgent",
            system_prompt=ARBITER_SYSTEM_PROMPT,
            schema_path=SCHEMAS_DIR / "tender_fit_report.schema.json",
        )

    def scout(
        self,
        *,
        keyword: str,
        days: int = 14,
        top_n: int = 30,
        data_path: str | None = None,
    ) -> ScoutResults:
        """Run ScoutAgent over local search results."""

        search_output = search_bids(
            keyword=keyword,
            days=days,
            top_n=top_n,
            data_path=data_path,
            cache_dir=self.cache_dir,
        )
        payload = {
            "query": keyword,
            "candidate_bids": search_output.model_dump(),
        }
        self.logger.info("scout.start", keyword=keyword, days=days, top_n=top_n)
        result = self._run_agent(self._scout, payload)
        self._validate_schema(self._scout.schema_path, result)
        return ScoutResults.model_validate(result)

    def collect(
        self,
        *,
        bid_id: str,
        doc_urls: list[str],
        out_dir: str | None = None,
    ) -> EvidenceManifest:
        """Run CollectorAgent: fetch docs then classify into a manifest."""

        artifacts_dir = Path(out_dir) if out_dir else self._bid_artifacts_dir(bid_id)
        docs_dir = artifacts_dir / "docs"
        fetch_output = fetch_docs(
            bid_id=bid_id,
            doc_urls=doc_urls,
            out_dir=str(docs_dir),
            cache_dir=self.cache_dir,
        )

        doc_inputs = []
        doc_index = 1
        for source_url in doc_urls:
            dest_path = self._doc_dest_from_url(source_url, docs_dir)
            if not dest_path.exists():
                continue
            doc_inputs.append(
                {
                    "doc_id": f"DOC-{doc_index:03d}",
                    "source_url": self._normalize_source_url(source_url),
                    "local_path": str(dest_path),
                    "filename": dest_path.name,
                }
            )
            doc_index += 1

        payload = {
            "bid_id": bid_id,
            "downloaded_docs": doc_inputs,
            "errors": fetch_output.errors,
        }
        self.logger.info("collector.start", bid_id=bid_id, doc_count=len(doc_inputs))
        result = self._run_agent(self._collector, payload)
        self._validate_schema(self._collector.schema_path, result)
        manifest = EvidenceManifest.model_validate(result)
        manifest = self._reconcile_manifest(manifest, doc_inputs)

        manifest_path = artifacts_dir / "evidence_manifest.json"
        self._write_json(manifest_path, manifest.model_dump())
        return manifest

    def extract(
        self,
        *,
        bid_id: str,
        manifest: EvidenceManifest,
        out_dir: str | None = None,
    ) -> tuple[TenderRequirements, list[dict[str, Any]]]:
        """Run ExtractorAgent over parsed + chunked text."""

        artifacts_dir = Path(out_dir) if out_dir else self._bid_artifacts_dir(bid_id)
        extracted_dir = artifacts_dir / "extracted"
        chunks = list(self._parse_and_chunk(manifest, extracted_dir))
        payload = {
            "bid_id": bid_id,
            "documents": [doc.model_dump() for doc in manifest.documents],
            "chunks": chunks,
        }
        self.logger.info("extractor.start", bid_id=bid_id, chunk_count=len(chunks))
        result = self._run_agent(self._extractor, payload)
        self._validate_schema(self._extractor.schema_path, result)
        requirements = TenderRequirements.model_validate(result)

        requirements_path = artifacts_dir / "tender_requirements.json"
        self._write_json(requirements_path, requirements.model_dump())
        return requirements, chunks

    def verify(
        self,
        *,
        bid_id: str,
        requirements: TenderRequirements,
        chunks: list[dict[str, Any]],
    ) -> list[VerifierReport]:
        """Run three independent verifier agents."""

        reports: list[VerifierReport] = []
        for verifier_id in ("A", "B", "C"):
            self.logger.info("verifier.start", bid_id=bid_id, verifier_id=verifier_id)
            payload = {
                "bid_id": bid_id,
                "verifier_id": verifier_id,
                "requirements": requirements.model_dump(),
                "chunks": chunks,
            }
            result = self._run_agent(self._verifier, payload)
            result["verifier_id"] = verifier_id
            self._validate_schema(self._verifier.schema_path, result)
            reports.append(VerifierReport.model_validate(result))
        return reports

    def arbitrate(
        self,
        *,
        bid_id: str,
        requirements: TenderRequirements,
        verifier_reports: list[VerifierReport],
        company_profile: dict[str, Any],
        reports_dir: str | None = None,
    ) -> tuple[TenderFitReport, str]:
        """Run ArbiterScorerAgent and render a Markdown report."""

        payload = {
            "bid_id": bid_id,
            "requirements": requirements.model_dump(),
            "verifier_reports": [report.model_dump() for report in verifier_reports],
            "company_profile": company_profile,
        }
        self.logger.info("arbiter.start", bid_id=bid_id)
        result = self._run_agent(self._arbiter, payload)
        self._validate_schema(self._arbiter.schema_path, result)
        report = TenderFitReport.model_validate(result)
        report_md = self._render_report_markdown(report)

        reports_path = Path(reports_dir) if reports_dir else PROJECT_ROOT / "reports"
        reports_path.mkdir(parents=True, exist_ok=True)
        self._write_json(
            reports_path / f"{bid_id}.json", report.model_dump(by_alias=True)
        )
        (reports_path / f"{bid_id}.md").write_text(report_md, encoding="utf-8")
        return report, report_md

    def evaluate_bid(
        self,
        *,
        bid_id: str,
        doc_urls: list[str],
        company_profile_path: str,
        artifacts_dir: str | None = None,
        reports_dir: str | None = None,
    ) -> tuple[TenderFitReport, str]:
        """Full end-to-end evaluation for a single bid."""

        manifest = self.collect(bid_id=bid_id, doc_urls=doc_urls, out_dir=artifacts_dir)
        requirements, chunks = self.extract(
            bid_id=bid_id, manifest=manifest, out_dir=artifacts_dir
        )
        verifier_reports = self.verify(
            bid_id=bid_id, requirements=requirements, chunks=chunks
        )
        company_profile = self._load_company_profile(company_profile_path)
        return self.arbitrate(
            bid_id=bid_id,
            requirements=requirements,
            verifier_reports=verifier_reports,
            company_profile=company_profile,
            reports_dir=reports_dir,
        )

    def _run_agent(self, agent: AgentSpec, payload: dict[str, Any]) -> dict[str, Any]:
        schema = self._load_schema(agent.schema_path)
        prompt = json.dumps(payload, ensure_ascii=True, indent=2)
        response_kwargs: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "system", "content": agent.system_prompt},
                {
                    "role": "user",
                    "content": f"Return JSON for {agent.name} using this input:\n{prompt}",
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": self._schema_name(schema),
                    "schema": schema,
                    "strict": True,
                }
            },
            "temperature": self.temperature,
        }
        if self.max_output_tokens is not None:
            response_kwargs["max_output_tokens"] = self.max_output_tokens
        response = self.client.responses.create(
            **response_kwargs,
        )
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> dict[str, Any]:
        if getattr(response, "output_parsed", None) is not None:
            return response.output_parsed

        raw = getattr(response, "output_text", None)
        if not raw:
            try:
                raw = response.output[0].content[0].text
            except (AttributeError, IndexError, TypeError):
                raw = None
        if not raw:
            raise RuntimeError("No output text returned from OpenAI response.")
        return json.loads(raw)

    def _validate_schema(self, schema_path: Path, data: dict[str, Any]) -> None:
        result = validate_schema(
            schema_path=str(schema_path),
            data=data,
            cache_dir=self.cache_dir,
        )
        if not result.valid:
            raise ValueError(f"Schema validation failed: {result.errors}")

    def _load_schema(self, schema_path: Path) -> dict[str, Any]:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        resolved = self._resolve_schema_refs(schema, schema_path.parent)
        return self._ensure_strict_schema(resolved)

    def _resolve_schema_refs(
        self, schema: Any, base_dir: Path
    ) -> dict[str, Any] | list | Any:
        if isinstance(schema, dict):
            if "$ref" in schema and isinstance(schema["$ref"], str):
                ref = schema["$ref"]
                if ref.endswith(".json"):
                    ref_path = base_dir / ref
                    ref_schema = json.loads(ref_path.read_text(encoding="utf-8"))
                    return self._resolve_schema_refs(ref_schema, base_dir)
            return {
                key: self._resolve_schema_refs(value, base_dir)
                for key, value in schema.items()
            }
        if isinstance(schema, list):
            return [self._resolve_schema_refs(item, base_dir) for item in schema]
        return schema

    def _ensure_strict_schema(self, schema: Any) -> Any:
        if isinstance(schema, dict):
            if "format" in schema:
                schema.pop("format", None)
            if schema.get("type") == "object" and "additionalProperties" not in schema:
                schema["additionalProperties"] = False
            if schema.get("type") == "object" and "properties" in schema:
                prop_keys = list(schema.get("properties", {}).keys())
                schema["required"] = prop_keys
            for key, value in list(schema.items()):
                schema[key] = self._ensure_strict_schema(value)
            return schema
        if isinstance(schema, list):
            return [self._ensure_strict_schema(item) for item in schema]
        return schema

    def _schema_name(self, schema: dict[str, Any]) -> str:
        title = schema.get("title", "StructuredOutput")
        return "".join(char for char in title if char.isalnum()) or "StructuredOutput"

    def _bid_artifacts_dir(self, bid_id: str) -> Path:
        path = PROJECT_ROOT / "artifacts" / bid_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _reconcile_manifest(
        self,
        manifest: EvidenceManifest,
        doc_inputs: list[dict[str, str]],
    ) -> EvidenceManifest:
        lookup = {doc["doc_id"]: doc for doc in doc_inputs}
        fetched_at = datetime.now(timezone.utc).isoformat()
        manifest.documents = [doc for doc in manifest.documents if doc.doc_id in lookup]
        for doc in manifest.documents:
            if doc.doc_id in lookup:
                doc.source_url = lookup[doc.doc_id]["source_url"]
                doc.local_path = lookup[doc.doc_id]["local_path"]
            if doc.fetched_at is None:
                doc.fetched_at = fetched_at
        if manifest.generated_at is None:
            manifest.generated_at = fetched_at
        return manifest

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )

    def _parse_and_chunk(
        self, manifest: EvidenceManifest, extracted_dir: Path
    ) -> Iterable[dict[str, Any]]:
        extracted_dir.mkdir(parents=True, exist_ok=True)
        pages_path = extracted_dir / "pages.jsonl"
        chunks_path = extracted_dir / "chunks.jsonl"

        pages_handle = pages_path.open("w", encoding="utf-8")
        chunks_handle = chunks_path.open("w", encoding="utf-8")

        try:
            for doc in manifest.documents:
                pages_output = parse_pdf(
                    pdf_path=doc.local_path,
                    cache_dir=self.cache_dir,
                )
                for page in pages_output.pages:
                    row = {
                        "doc_id": doc.doc_id,
                        "doc_type": doc.doc_type,
                        "source_url": doc.source_url,
                        "page_num": page.page_num,
                        "text": page.text,
                    }
                    pages_handle.write(json.dumps(row, ensure_ascii=True) + "\n")

                chunk_output = chunk_text(
                    pages=[page.model_dump() for page in pages_output.pages],
                    cache_dir=self.cache_dir,
                )
                for chunk in chunk_output.chunks:
                    row = {
                        "chunk_id": chunk.chunk_id,
                        "doc_id": doc.doc_id,
                        "doc_type": doc.doc_type,
                        "source_url": doc.source_url,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "text": chunk.text,
                    }
                    chunks_handle.write(json.dumps(row, ensure_ascii=True) + "\n")
                    yield row
        finally:
            pages_handle.close()
            chunks_handle.close()

    def _doc_dest_from_url(self, source_url: str, out_dir: Path) -> Path:
        parsed = urlparse(source_url)
        if parsed.scheme in ("", "file"):
            filename = Path(parsed.path if parsed.scheme == "file" else source_url).name
        else:
            filename = Path(parsed.path).name or "document.pdf"
        return out_dir / filename

    def _normalize_source_url(self, source_url: str) -> str:
        parsed = urlparse(source_url)
        if parsed.scheme in ("", "file"):
            path = Path(parsed.path if parsed.scheme == "file" else source_url).resolve()
            return path.as_uri()
        return source_url

    def _load_company_profile(self, profile_path: str) -> dict[str, Any]:
        payload = json.loads(Path(profile_path).read_text(encoding="utf-8"))
        schema_path = SCHEMAS_DIR / "company_profile.schema.json"
        self._validate_schema(schema_path, payload)
        profile = CompanyProfile.model_validate(payload)
        return profile.model_dump(by_alias=True)

    def _render_report_markdown(self, report: TenderFitReport) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# Tender Fit Report: {report.bid_id}",
            "",
            f"- Decision: {report.decision}",
            f"- Fit Score: {report.fit_score:.1f}",
            f"- Generated: {timestamp}",
            "",
        ]
        if report.summary:
            lines.append("## Summary")
            lines.append(report.summary)
            lines.append("")

        eligibility = report.eligibility
        lines.append("## Eligibility")
        lines.append(f"- Pass: {eligibility.passed}")
        for reason in eligibility.reasons:
            lines.append(f"- {reason.requirement_id}: {reason.status} - {reason.notes}")
        lines.append("")

        if report.gaps:
            lines.append("## Gaps")
            for gap in report.gaps:
                lines.append(f"- {gap}")
            lines.append("")

        lines.append("## Citations")
        for citation in report.citations:
            lines.append(
                f"- [{citation.doc_type}] {citation.source_url} p{citation.page}: {citation.quote}"
            )
        lines.append("")
        return "\n".join(lines)
