# Security & Compliance

## Data handling
- Store API key in environment variables only.
- Do not commit keys or downloaded PDFs into git.

## Public-only rule
- Only fetch documents accessible without login.
- Stop if redirected to login.

## Operational safety
- Add rate limiting and retry with backoff.
- Cache downloads to avoid repeated hits.

## Model safety
- Verifiers must reject uncited claims.
- Never claim "eligible" without checking all hard requirements.
