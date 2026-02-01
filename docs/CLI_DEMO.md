# CLI Demo Flow

This document describes how the TenderFit CLI demo is wired, what happens at each stage, and how the end-to-end flow works.

## Entry Point

Run the demo via:

```bash
python3 -m tenderfit.cli demo
```

The `tenderfit.cli` module dispatches to `run_demo()` in `tenderfit/demo.py`.

## High-Level Flow

The demo is an interactive guided run that orchestrates the multi-agent pipeline in this order:

1. **Scout** (BidPlus scan with LLM filtering)
2. **Collector** (download bid docs + corrigenda)
3. **Extractor** (pull key fields)
4. **Verifier** (parallel verifiers with citations)
5. **Arbiter** (resolve, score, and shortlist)
6. **Shortlist** (CSV output + best bid)

The demo is designed to:

- Show human-readable logs at each stage
- Render progress bars and status markers
- Provide mascot-driven narration
- Gracefully handle no-result cases

## Scout (Scan)

The demo runs the CLI `scan` subcommand with LLM filtering enabled. This is implemented in:

- `tenderfit/cli.py` — `scan` command wiring
- `tenderfit/tools/bidplus_scout.py` — BidPlus browsing + candidate collection + LLM filter

The scan step:

1. Navigates to BidPlus using the agent-browser runtime.
2. Searches and paginates results.
3. Produces a candidate list.
4. Applies LLM-based filtering (OpenAI client, `gpt-4.1-mini`).
5. Writes listings to `artifacts/<bid_id>/listing.json`.

The demo prints a short JSON summary for the scan output and collects it for the next stage.

## Collector (Fetch)

After the scan returns a list of bids, the demo fetches docs for the top bids in parallel.

- `tenderfit/cli.py` — `fetch` command wiring
- `tenderfit/tools/bidplus_collect_docs.py` — agent-browser download flow

Collector behavior:

1. Uses the listing to discover document links.
2. Downloads base bid documents and corrigenda.
3. Writes an `evidence_manifest.json` under `artifacts/<bid_id>/`.

In demo mode, up to the top 3 bids are processed in parallel.

## Evaluator (Extract + Verify)

The evaluator is an orchestrated chain of agents:

- **Extractor**: pulls fields and evidence references.
- **Verifiers**: three parallel verifiers with citation checks.
- **Arbiter**: merges verifier outputs into a decision.

Implementation:

- `tenderfit/orchestrator.py`
- `tenderfit/agents/*`

Each bid is processed independently. Results are written to:

- `reports/<bid_id>.json`
- `reports/<bid_id>.md`

## Arbiter + Shortlist

After the evaluator finishes for all bids:

- Arbiter is shown as a global step (not per bid).
- Shortlist collects the report JSON files and produces a CSV output.

Implementation:

- `tenderfit/cli.py` — `shortlist` command
- `tenderfit/shortlists/` — output directory

The demo surfaces:

- Best match from the CSV
- Path to the generated shortlist file

## Demo UX

The demo includes:

- ASCII art mascot and banners
- Stage-specific progress bars
- Per-bid pipeline status (collector/extractor/verifier/arbiter)
- Witty remarks at completion (success/empty/low-fit cases)

This logic is implemented inside `tenderfit/demo.py`.

## Failure Modes

Common demo failure cases and how they are handled:

- **No bids returned**: Demo prints a message and exits gracefully.
- **Missing API key**: LLM filter fails if `OPENAI_API_KEY` is unset.
- **Collector failure**: Bid-level fetch errors are logged; demo continues.

## Key Files

- `tenderfit/demo.py` — demo orchestration + UI/ASCII output
- `tenderfit/cli.py` — command wiring
- `tenderfit/tools/bidplus_scout.py` — live BidPlus scanning
- `tenderfit/tools/bidplus_collect_docs.py` — document collection
- `tenderfit/orchestrator.py` — multi-agent pipeline

