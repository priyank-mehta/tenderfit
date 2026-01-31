---
name: add-tool
description: Add a new tool function with schema, caching, and unit tests
metadata:
  short-description: Add tool + schema + tests
---

Given tool name and I/O:
- Implement in tenderfit/tools/<tool>.py
- Add Pydantic model for inputs/outputs
- Ensure tool output can be validated against a schema
- Add tests (happy path + failure)
- Update docs/TOOLS_AND_SKILLS.md
