# TenderFit (Vehicle Hiring) — Multi-Agent Tender Research & Fit Scoring

TenderFit scouts public GeM / BidPlus tenders for vehicle hiring (cab/taxi/SUV/MUV), collects bid documents and corrigenda, extracts eligibility and SLA constraints with citations, and scores Go/No-Go fit against a fleet operator profile.

## Why this is Track-3 worthy
This is not a single-agent summarizer. TenderFit uses a coordinated multi-agent workflow with verification and consensus:
- Scout (find relevant tenders)
- Collector (fetch docs + corrigenda with precedence)
- Extractor (structured extraction)
- Verifiers (independent citation checks)
- Arbiter + Fit Scorer (consensus + ranking + gap checklist)

## Modes
### CLI
- `python3 -m tenderfit.cli scan --keywords "cabs taxi" --days 14 --top 30 --max-pages 20 --llm-filter`
- `python3 -m tenderfit.cli fetch --bid-id <ID> --out artifacts/<ID>/`
- `python3 -m tenderfit.cli evaluate --bid-id <ID> --company examples/company_profile.example.json --out reports/<ID>.md`
- `python3 -m tenderfit.cli shortlist --company examples/company_profile.example.json --top 10 --out shortlists/shortlist.csv`
- Demo flow: `python3 -m tenderfit.cli demo`

### Web UI
The React UI mirrors the CLI demo flow with live pipeline progress, per-bid lanes,
and shortlist insights.
- Start API: `python3 -m tenderfit.web.server`
- Start UI: `cd tenderfit-ui && npm run dev`
- Open: `http://localhost:5173`

## Data policy
We only fetch publicly accessible bid documents and do not require login.

## Information flow
1) Scout searches BidPlus listings (tokenized keywords + LLM filter).
2) Collector fetches bid docs and corrigenda with precedence.
3) Extractor pulls structured requirements with citations.
4) Verifiers independently check evidence + quotes.
5) Arbiter resolves conflicts and assigns fit scores.
6) Shortlist ranks bids and emits CSV.

## Tech stack
- Python 3.11+, FastAPI (API + SSE), Pydantic
- OpenAI API (LLM filtering + evaluation)
- agent-browser (BidPlus navigation + document capture)
- React + Vite (Web UI)

## Setup
1) Python 3.11+ and Node 18+
2) Create a virtualenv and install Python deps:
   - `pip install -e .`
3) Install agent-browser:
   - `npm install -g agent-browser`
   - `agent-browser install`
4) Set API key:
   - `export OPENAI_API_KEY=...`
5) Install UI deps:
   - `cd tenderfit-ui && npm install`

## Evals
Run agent eval suites:
- `python3 -m tenderfit.cli eval --suite quick`
- `python3 -m tenderfit.cli eval --suite scout`
- `python3 -m tenderfit.cli eval --suite collector`
- `python3 -m tenderfit.cli eval --suite extractor`
- `python3 -m tenderfit.cli eval --suite verifier`
- `python3 -m tenderfit.cli eval --suite arbiter`
- `python3 -m tenderfit.cli eval --suite shortlist`
See `tenderfit/evals/README.md` for details.

## Credits / Dependencies
- OpenAI API (LLM scoring, filtering)
- agent-browser (vercel-labs/agent-browser)
- FastAPI + Uvicorn
- Pydantic
- React + Vite
