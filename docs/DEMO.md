# Demo Script (2 minutes)

## Setup
- company_profile.example.json ready
- choose keywords: "cab taxi hiring SUV MUV monthly basis"

## Live steps
1) Run: tenderfit scan --days 14 --top 20
2) Pick 1 bid with corrigendum, 1 without
3) Run: tenderfit evaluate --bid-id <A> ...
4) Show output:
   - FitScore
   - Go/No-Go
   - Top blockers with citations
5) Open a cited quote in the PDF text output (page anchor)
6) Repeat quickly for <B> and show different outcome

## Judge punchline
"This is a decision agent with proof, not a summarizer."
