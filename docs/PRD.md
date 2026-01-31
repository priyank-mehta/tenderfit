# PRD — TenderFit (Vehicle Hiring)

## 1. Problem
MSME fleet operators waste days reading tender PDFs and still miss:
- hidden eligibility constraints,
- SLA penalties,
- corrigendum overrides,
leading to wasted bids and disqualifications.

## 2. Target Users
- Small travel agencies / fleet operators (10–200 cars)
- Taxi vendors bidding for government cab hiring
- Operations manager / owner making Go/No-Go decisions

## 3. MVP Outcomes (must hit)
- Find relevant vehicle-hiring tenders
- Extract "apply/no-apply" reasons with clause citations
- Rank top tenders by FitScore

## 4. Scope (MVP)
### In-scope
- Public tender discovery (BidPlus pages)
- Bid doc + corrigendum retrieval
- PDF text extraction + page anchors
- Structured requirement extraction (schemas)
- Company profile comparison (Go/No-Go + gaps)
- CLI + Markdown report + CSV shortlist

### Out of scope
- Bid submission
- Login workflows
- Price quoting / cost optimization
- Notifications / scheduler

## 5. Key User Stories
1) As a vendor, I want a shortlist of tenders I should apply to this week.
2) As a vendor, I want to know exactly why a tender is No-Go with page citations.
3) As a vendor, I want a gap checklist (what docs/criteria are missing).

## 6. Success Metrics (demo-day)
- Coverage: scans 30 bids in <2 minutes (network dependent)
- Correctness: >= 90% of extracted eligibility fields have correct citations
- Robustness: detects corrigendum overrides and flags contradictions
- Judge wow: produces 1 Go + 1 No-Go with proof in 2 minutes

## 7. Agentic Differentiation
- Independent verifiers must reject uncited claims
- Arbiter merges verifier votes into final consensus
- Trace is exportable (what was retrieved, extracted, verified)

## 8. Deliverables
- CLI tool
- JSON outputs (schemas)
- Markdown decision memo
- CSV shortlist
