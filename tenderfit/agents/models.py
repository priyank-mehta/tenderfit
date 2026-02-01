"""Pydantic models mirroring TenderFit JSON schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_url: str
    doc_type: Literal["base", "sla", "atc", "corrigendum", "other"]
    page: int
    quote: str
    anchor: str
    notes: str | None = None


class Requirement(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    category: Literal[
        "eligibility",
        "sla",
        "technical",
        "financial",
        "documents",
        "submission",
        "other",
    ]
    requirement: str
    mandatory: bool | None = None
    citations: list[Citation]
    notes: str | None = None


class TenderRequirements(BaseModel):
    model_config = ConfigDict(extra="allow")

    bid_id: str
    title: str | None = None
    closing_date: str | None = None
    requirements: list[Requirement]


class EligibilityReason(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_id: str
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW"]
    notes: str
    citations: list[Citation]


class EligibilityBlock(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    passed: bool = Field(alias="pass")
    reasons: list[EligibilityReason]


class TenderFitReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    bid_id: str
    decision: Literal["GO", "NO_GO", "NEEDS_REVIEW"]
    fit_score: float = Field(ge=0, le=100)
    summary: str | None = None
    eligibility: EligibilityBlock
    gaps: list[str]
    citations: list[Citation]
    requirements_reviewed: list[str] | None = None


class BidCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    bid_id: str
    title: str
    closing_date: str | None = None
    links: list[str] = Field(default_factory=list)
    summary: str | None = None


class ScoutResults(BaseModel):
    model_config = ConfigDict(extra="allow")

    query: str
    bids: list[BidCandidate]
    notes: str | None = None


class EvidenceDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    doc_id: str
    source_url: str
    local_path: str
    doc_type: Literal["base", "sla", "atc", "corrigendum", "other"]
    title: str | None = None
    fetched_at: str | None = None


class EvidenceManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    bid_id: str
    generated_at: str | None = None
    documents: list[EvidenceDocument]


class VerifierResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_id: str
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW"]
    notes: str
    citations: list[Citation] | None = None


class VerifierSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    passed: int
    failed: int
    needs_review: int


class VerifierReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    bid_id: str
    verifier_id: str
    summary: VerifierSummary
    results: list[VerifierResult]


class FleetProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    sedan: int
    suv: int
    muv: int
    hatchback: int
    model_year_min: int


class DocsProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    gst: bool | None = None
    pan: bool | None = None
    permits: bool | None = None
    insurance: bool | None = None


class FinancialsProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    turnover_last_3y_inr: list[float]


class ExperienceProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    govt_contracts_count: int | None = None
    similar_work_years: float | None = None


class OperationsProfile(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cities_served: list[str] | None = None
    drivers_available: int | None = None
    twenty_four_seven_capable: bool | None = Field(default=None, alias="24x7_capable")


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    company_name: str
    fleet: FleetProfile
    docs: DocsProfile
    financials: FinancialsProfile
    experience: ExperienceProfile
    operations: OperationsProfile
