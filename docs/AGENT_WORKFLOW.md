# Multi-Agent Workflow

## 1) ScoutAgent (Discovery)
Input: keywords, region(optional), timeframe
Output: candidate bids list with bid_id, title, closing_date, links

## 2) CollectorAgent (Evidence pack)
Input: bid_id
Actions:
- download bid docs + attachments + corrigenda
- label each doc: base | atc | sla | corrigendum
Output: evidence_manifest.json

## 3) ExtractorAgent (Structured reader)
Input: extracted text chunks + manifest
Output: tender_requirements.json (schema) with citations

## 4) Verifier agents (Independent auditors)
Input: tender_requirements.json + chunks
Output: verifier_report_{A,B,C}.json
Rules:
- reject any requirement missing citation
- flag contradictions (corrigendum vs base)
- quote must match source chunk text

## 5) ArbiterScorerAgent (Consensus + Fit)
Input: all verifier reports + company_profile.json
Output:
- tender_fit_report.json (schema)
- report.md (human-readable)
