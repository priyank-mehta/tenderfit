# Repository Guidelines

# Project Instructions for Codex (TenderFit)

## Goal
Build a CLI-first, multi-agent MVP that:
1) scans GeM BidPlus for vehicle-hiring tenders,
2) fetches bid docs + corrigenda,
3) parses PDFs -> chunked text with page anchors,
4) extracts eligibility/SLA requirements as structured JSON with citations,
5) compares to company profile -> Go/No-Go + FitScore + gaps,
6) outputs a ranked shortlist and a decision memo.

## Non-negotiables
- Deterministic structured outputs using JSON schemas in /schemas.
- Every extracted requirement must carry at least one citation:
  {source_url, doc_type, page, quote, anchor}.
- Corrigendum precedence: if corrigendum conflicts with base doc, corrigendum wins.
- CLI-first: no web UI for MVP.

## Implementation constraints
- Python only.
- Use OpenAI Responses API + Agents SDK for the multi-agent orchestration.
- Use Pydantic models mirroring JSON schemas.
- Prefer small, testable modules:
  tenderfit/agents, tenderfit/tools, tenderfit/storage.

## Coding standards
- Type hints everywhere.
- No gigantic functions. Prefer pure functions.
- Logging via `structlog` or stdlib logging.
- Store artifacts under ./artifacts/<bid_id>/ (html, pdf, extracted text, index).
- Store outputs under ./reports/ and ./shortlists/.

## Delivery checklist
- `tenderfit scan` works for at least 20 bids.
- `tenderfit evaluate` produces valid JSON matching tender_fit_report.schema.json.
- `tenderfit evaluate` also writes a readable Markdown report with inline citations.
- Add minimal eval prompts in tenderfit/evals/ to catch hallucinations.

## What to avoid
- Don't add features not required by PRD.
- No paid data sources.
- No scraping behind login.


## Project Structure & Module Organization
This repository is currently empty (no tracked source files or directories). When you add code, keep a clean, predictable layout. A common structure is:

- `src/` for application code
- `tests/` for automated tests
- `assets/` for static files (images, fixtures)
- `scripts/` for developer utilities

Document any deviations in this file so contributors know where to look.

## Build, Test, and Development Commands
No build or test commands are defined yet. Once tooling is added, list the canonical commands here. Examples to document when available:

- `npm run dev` for local development
- `npm test` for running the test suite
- `npm run lint` for static analysis

## Coding Style & Naming Conventions
No style guide or linters are configured. When you introduce them, record the rules here. Recommended defaults:

- Indentation: 2 spaces for JS/TS, 4 spaces for Python
- File naming: `kebab-case` for folders, `camelCase` for variables, `PascalCase` for components/classes
- Prefer automated formatting (e.g., Prettier, Black, gofmt) and make it part of CI

## Testing Guidelines
No testing framework is configured. When tests are added, specify:

- Framework (e.g., Jest, Pytest, Go test)
- Naming conventions (e.g., `*.test.ts`, `test_*.py`)
- How to run tests locally and in CI

## Commit & Pull Request Guidelines
No repository history is available to infer conventions. Until standards are established:

- Use clear, imperative commit messages (e.g., "Add vehicle search filters")
- Keep PRs focused and describe changes, rationale, and testing
- Link related issues and add screenshots for UI changes

## Security & Configuration Tips
Store secrets in environment variables and exclude them from version control. If you add a `.env` file, include a `.env.example` with safe defaults.
