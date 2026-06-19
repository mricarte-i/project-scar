#!/usr/bin/env bash
# A simple script to run integration tests against a real PostgreSQL database in Docker.
# sets SCAR_DATABASE_URL env var, runs pytest, and cleans up the container when done.
# Usage:
#   ./scripts/test_integration.sh [pytest args] [--keep]
#   --keep: if set, the database container will not be stopped after tests, 
#       allowing you to inspect it manually. 
#       You can stop it later with `docker stop scar-test-db`.
#
# Note: the script assumes the database container is named `scar-test-db` and listens on port 5432.
set -euo pipefail

CONTAINER=scar-test-db
PORT=5432
DB_URL="postgresql+psycopg://scar:scar@localhost:${PORT}/scar"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- PARSE ARGS ---
KEEP=0
PYTEST_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--keep" ]]; then
        KEEP=1
    else
        PYTEST_ARGS+=("$arg")
    fi
done

if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
    PYTEST_ARGS=(tests/integration)
fi

command -v docker > /dev/null 2>&1 || {
    echo "error: docker not found. Install Docker"
    exit 1
}

# Prefer the project venv's python; fallback to whatever's on PATH
PYTHON="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python"

# --- START THE DB CONTAINER ---
STARTED=0
if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "Reusing running container $CONTAINER"
else
    echo "Starting new container $CONTAINER"
    docker run --rm -d --name "$CONTAINER" -p "${PORT}:5432" \
        -e POSTGRES_USER=scar -e POSTGRES_PASSWORD=scar -e POSTGRES_DB=scar \
        postgres:16 > /dev/null
    STARTED=1
fi

cleanup() {
    if [[ "$STARTED" -eq 1 && "$KEEP" -eq 0 ]]; then
        echo "Stopping container $CONTAINER"
        docker stop "$CONTAINER" > /dev/null
    elif [[ "$STARTED" -eq 1 && "$KEEP" -eq 1 ]]; then
        echo "Keeping container $CONTAINER running (--keep)."
        echo "To stop it manually, run:" 
        echo "  docker stop $CONTAINER"
    fi
}
trap cleanup EXIT

# --- WAIT FOR DB TO BE READY ---
printf "Waiting for database to be ready"
echo
for i in $(seq 1 30); do
    printf "."
    if docker exec "$CONTAINER" pg_isready -U scar -d scar -h 127.0.0.1 > /dev/null 2>&1; then
        echo
        echo "Database is ready!"
        break
    fi
    if [[ "$i" -eq 30 ]]; then
        echo
        echo "Database did not become ready in time. Exiting."
        exit 1
    fi
    sleep 1
done

# --- RUN THE TESTS ---
export SCAR_DATABASE_URL="$DB_URL"
echo "SCAR_DATABASE_URL set to $DB_URL"
echo "Running integration tests with pytest..."
echo

cd "$REPO_ROOT"
set +e
"$PYTHON" -m pytest "${PYTEST_ARGS[@]}"
RC=$?
set -e
exit "$RC"