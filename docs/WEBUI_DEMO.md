# Web UI Demo Flow

This document maps the CLI demo flow to the React-based Web UI and explains how the pipeline is rendered in the browser.

## Entry Points

Start the backend API:

```bash
python3 -m tenderfit.web.server
```

Start the React UI:

```bash
cd tenderfit-ui
npm run dev
```

Open: `http://localhost:5173`

## High-Level Mapping

The Web UI mirrors the CLI demo stages:

1. **Scout** → Step 1 in the UI, driven by `Run Full Pipeline`.
2. **Collector** → Step 2, rendered as per‑bid lanes (no raw logs).
3. **Evaluator** → Step 3, per‑bid lanes and stage chips.
4. **Arbiter** → Step 4, global progress bar and insights.

The UI does not show raw logs; instead it shows:

- Live pipeline state
- Per‑bid stage chips
- Narrative feed (mascot voice)

## Scout (Step 1)

The Scout form accepts the same inputs as the CLI `scan` command:

- Keywords
- Days / Top / Max pages
- LLM filter options

Click **Run Full Pipeline**:

- The Scout form swaps to **Pipeline Live**.
- The progress bar fills as stages advance.
- A “Mission Control” narrative panel describes what is happening.

When no bids are returned:

- The log area is replaced with a “No bids returned” message.
- A toast message is shown at the top-right.

## Collector + Evaluator (Steps 2–3)

Collector and Evaluator share a unified “bid lanes” view:

- Each bid becomes a lane card.
- Stage chips show status:
  - `⏳` running
  - `✅` done
  - `⛔` error
- No raw logs are displayed.

When multiple bids are processed, lanes update independently.

## Arbiter + Shortlist (Step 4)

After all evaluations complete:

- The Arbiter progress bar appears.
- Shortlist results are displayed.
- The best bid is summarized.

## UX Parity with CLI Demo

The Web UI reuses the CLI demo’s intent but translates it to a visual format:

- **Mascot narration** → “Mission Control” feed
- **Progress bars** → Pipeline Live progress + Arbiter bar
- **Per-bid progress** → Lanes with status chips
- **Interactive flow** → Single “Run Full Pipeline” action

## Implementation References

- `tenderfit-ui/src/App.jsx` — UI workflow + pipeline orchestration
- `tenderfit-ui/src/App.css` — visual system
- `tenderfit/web/server.py` — backend API (jobs + SSE events)

