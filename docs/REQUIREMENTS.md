# Requirements (MVP)

## Functional
R1. Scan public tender listings for vehicle hiring.
R2. Fetch all docs (bid doc, ATC/SLA attachments, corrigenda).
R3. Parse PDFs into page-anchored chunks.
R4. Extract structured requirements per schema with citations.
R5. Compare to company profile and compute:
    - Eligibility: pass/fail
    - FitScore 0–100
    - Gaps checklist
R6. Output:
    - tender_fit_report.json
    - report.md
    - shortlist.csv

## Non-functional
N1. No hallucinated requirements: every requirement must cite source.
N2. Corrigendum precedence rule implemented.
N3. Re-runnable with local cache.
N4. CLI errors must be actionable.

## Compliance/Safety
C1. Public documents only.
C2. Respect site terms/robots where applicable.
C3. Rate-limit requests; cache downloads.
