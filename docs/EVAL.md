# Evals (MVP)

## What we test
1) Citation coverage:
   - % of requirements with >=1 valid citation
2) Quote fidelity:
   - quoted evidence appears verbatim in parsed chunk text
3) Corrigendum precedence:
   - if corrigendum changes a field, final output reflects corrigendum
4) No-go correctness:
   - if turnover/experience missing, output must mark No-Go and cite clause

## Minimal prompt set (10–20 cases)
- 5 explicit vehicle-hiring bids
- 3 with corrigenda
- 2 negative controls (non-vehicle category)

## Output gating
Fail build if:
- citation_coverage < 0.9
- any "hard requirement" is uncited
