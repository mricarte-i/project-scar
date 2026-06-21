#!/usr/bin/env bash
#
# Usage:
#   ./scripts/smoke-test.sh         # smoke a stack alraedy running at $BASE_URL
#   ./scripts/smoke-test.sh --up    # `docker compose up -d --build` first, then tear fown after
#
# Env overrides:
#   BASE_URL (default http://localhost:8000)
#   API_KEY (default dev-key > matches docker-compose's SCAR_ADMIN_API_KEY)
#   SAT     (default smoke-$$ > unique per run so re-runs don't collide)
set -eup pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-dev-key}"
SAT="${SAT:-smoke-$$}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UP=0
[[ "${1:-}" == "--up" ]] && UP=1

cd "$REPO_ROOT"

# compose is only needed for --up
COMPOSE=""
resolve_compose() {
    if docker compose version > /dev/null 2>&1; then
        COMPOSE="docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE="docker-compose"
    else
        echo "error: --up needs Docker Compose ('docker compose' v2 plugin or the" \
                "'docker-compose' binary). Install it, or start the stack yourself" \
                "(docker compose up -d) and run this script without --up." >&2
        exit 1
    fi
}

TMP=""
cleanup() {
    local rc=$?
    [[ -n "$TMP" ]] && rm -rf "$TMP"
    if [[ $UP -eq 1 && -n "$COMPOSE" ]]; then
        [[ "$rc" -ne 0 ]] && { echo "--- compose logs ---"; $COMPOSE logs >&2 || true; }
        echo "Tearing down stack ($COMPOSE down -v)..."
        $COMPOSE down -v >/dev/null 2>&1 || true
    fi
    exit "$rc"
}
trap cleanup EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

if [[ $UP -eq 1 ]]; then
    resolve_compose
    echo "Bringing up stack with $COMPOSE..."
    $COMPOSE up -d --build
fi

# --- wait for liveness ---
printf "Waiting for %s/healthz" "$BASE_URL"
echo
for i in $(seq 1 30); do
    if curl -fs "$BASE_URL/healthz" > /dev/null 2>&1; then 
        echo " OK"
        break
    fi
    [[ "$i" -eq 30 ]] && { echo " timed out." >&2; exit 1; }
    printf "."; sleep 2
done

TMP="$(mktemp -d)"

# --- JSON asset: multipart upload -> resolve (the path that used to 500) ---
printf '{"gain": 4.27}' > "$TMP/payload.json"
json_url="$BASE_URL/admin/v1/satellites/$SAT/assets/vicarious_cal_gains/versions"
echo "POST json asset (multipart) -> $json_url"
curl -fsS -X POST "$json_url" \
    -H "X-API-Key: $API_KEY" \
    -F "valid_from=2025-01-01T00:00:00Z" \
    -F "file=@$TMP/payload.json;type=application/json" >/dev/null \
    || fail "Failed to upload JSON asset (write path broken?)"

echo "GET resolve ..."
got="$(curl -fsS -L "$BASE_URL/v1/satellites/$SAT/assets/vicarious_cal_gains?at=2025-01-02T00:00:00Z")" \
    || fail "Failed to resolve JSON asset (read path broken?)"
# the resolved version must carry a presigned blob URL (real MinIO round-trip)
echo "$got" | grep -q '"url"' || fail "resolve response missing payload url: $got"

echo "SMOKE TEST PASSED OK: health + multipart upload + resolve all worked"