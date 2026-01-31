---
name: add-eval
description: Add eval prompts and a small harness to measure citation fidelity and corrigendum precedence
metadata:
  short-description: Add eval set + harness
---

You will:
- Add 10–20 eval cases in tenderfit/evals/
- Implement checks for citation coverage and quote fidelity
- Provide a CLI command: tenderfit eval --suite quick
- Fail eval if citation coverage < 0.9
