#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${OPENAI_API_KEY:-}" && -f ".env" ]]; then
  set -a
  source .env
  set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is not set. Add it to .env or export it before running the demo."
  echo "Example: export OPENAI_API_KEY=\"sk-...\""
  exit 1
fi

python3 -m tenderfit.cli demo
