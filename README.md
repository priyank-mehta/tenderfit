# TenderFit (Vehicle Hiring) — Multi-Agent Tender Research & Fit Scoring (CLI-first)

TenderFit scans public GeM/GeM BidPlus tenders for vehicle hiring (cab/taxi/SUV/MUV),
collects all bid docs + corrigenda, extracts eligibility/SLA constraints with citations,
and scores "Go/No-Go" fit against an MSME fleet operator profile.

## Why this is Track-3 worthy
This is not a single-agent summarizer.
We use a coordinated multi-agent workflow with verification/consensus:
- Scout (find relevant tenders)
- Collector (fetch docs + corrigenda with precedence)
- Extractor (structured extraction)
- Verifiers (independent citation checks)
- Arbiter + Fit Scorer (consensus + ranking + gap checklist)

## CLI (MVP)
- tenderfit scan --keywords "cab taxi hiring SUV MUV" --days 14 --top 30
- tenderfit fetch --bid-id <ID> --out artifacts/<ID>/
- tenderfit evaluate --bid-id <ID> --company examples/company_profile.example.json --out reports/<ID>.md
- tenderfit shortlist --company examples/company_profile.example.json --top 10 --out shortlist.csv

## Data policy
We only fetch publicly accessible bid documents and do not require login.

## Dev setup
1) Python 3.11+
2) Create venv, install deps (poetry or pip)
3) Set OPENAI_API_KEY in env
4) Run:
   - python -m tenderfit.cli --help
