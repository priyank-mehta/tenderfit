# Tools (runtime) and Skills (Codex)

## Runtime tools (Agents SDK tool-calls)
- tool.search_bids (local listing search with cache)
- tool.fetch_docs (download bid docs with cache)
- tool.parse_pdf (extract page text from PDFs)
- tool.chunk_text (chunk pages into anchored spans)
- tool.retrieve (vector search or lexical search)
- tool.validate_schema (JSON schema validation with cache)
- tool.render_report

## Codex skills (developer acceleration)
We provide reusable Codex skills under .codex/skills/ so you can:
- scaffold the repo consistently
- add a new agent with wiring
- add a tool with schema + tests
- add eval prompts and run them
