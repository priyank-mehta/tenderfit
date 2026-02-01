# TenderFit Eval Suites

Run evals with:

```bash
python3 -m tenderfit.cli eval --suite quick
```

## Suites

- quick: Smoke test covering each agent
- scout: Scout keyword/date matching cases
- collector: Collector doc + corrigendum precedence cases
- extractor: Extractor field capture cases
- verifier: Verifier citation fidelity cases
- arbiter: Arbiter decision + scoring cases
- shortlist: Shortlist ranking + summary cases

## Commands

```bash
python3 -m tenderfit.cli eval --suite scout
python3 -m tenderfit.cli eval --suite collector
python3 -m tenderfit.cli eval --suite extractor
python3 -m tenderfit.cli eval --suite verifier
python3 -m tenderfit.cli eval --suite arbiter
python3 -m tenderfit.cli eval --suite shortlist
```

## Coverage Threshold

The eval runner fails if overall coverage is below 0.90. Override with:

```bash
python3 -m tenderfit.cli eval --suite quick --min-coverage 0.95
```
