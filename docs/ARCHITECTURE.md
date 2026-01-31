# Architecture

## High-level
CLI -> Orchestrator (Agents SDK) -> Tools -> Storage -> Outputs

### Storage layers
- artifacts/<bid_id>/
  - listing.html
  - docs/*.pdf
  - extracted/pages.jsonl
  - index/faiss/ (optional)
- reports/
  - <bid_id>.json
  - <bid_id>.md
- shortlists/
  - shortlist.csv

## Tools (code)
- search_bids(keyword, days, top_n) -> list[bids]
- fetch_bid_docs(bid_id) -> downloads pdf urls
- parse_pdf(pdf_path) -> {page_num: text}
- chunk_pages(pages) -> chunks with anchors
- index_chunks(chunks) -> vector index (optional MVP-lite)
- extract_requirements(chunks) -> tender_requirements.json
- verify_citations(requirements, chunks) -> verifier_votes
- score_fit(requirements, company_profile) -> tender_fit_report.json

## Agents (runtime)
- ScoutAgent
- CollectorAgent
- ExtractorAgent
- VerifierAgentA/B/C
- ArbiterScorerAgent

## Determinism anchors
- Structured outputs (schemas)
- Citation requirement
- Verifier quorum
