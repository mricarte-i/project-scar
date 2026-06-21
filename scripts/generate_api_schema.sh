#!/usr/bin/env bash
# Dump the FastAPI schema to docs/openapi.json
#
# Usage:
#   ./scripts/generate_api_schema.sh                   # -> docs/openapi.json
#   ./scripts/generate_api_schema.sh path/to/output.json
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO_ROOT/docs/openapi.json}"

# Prefer the project venv's python; fallback to whatever's on PATH
PYTHON="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python"

mkdir -p "$(dirname "$OUT")"

cd "$REPO_ROOT"
"$PYTHON" - "$OUT" <<'PY'
import json
import sys

from app.main import app

out = sys.argv[1]
with open(out, "w") as f:
    json.dump(app.openapi(), f, indent=2)
    f.write("\n")
print(f"Wrote OpenAPI schema to {out}")
PY