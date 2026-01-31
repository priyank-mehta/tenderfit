---
name: add-agent
description: Add a new runtime agent (Agents SDK) with a prompt, wiring, and tests
metadata:
  short-description: Add new agent end-to-end (prompt + wiring)
---

Given an agent name and responsibilities:
- Create tenderfit/agents/<agent_name>.py
- Add prompt template to docs/PROMPTS.md
- Wire into orchestrator in tenderfit/app.py
- Add minimal unit test stub in tenderfit/evals/
- Update docs/AGENT_WORKFLOW.md if workflow changes
