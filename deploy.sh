#!/usr/bin/env bash
# One-command deployment for the FastAPI + PostgreSQL Docker Compose stack.
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

force_rebuild=false
skip_smoke=false
for argument in "$@"; do
  case "$argument" in
    --rebuild) force_rebuild=true ;;
    --no-smoke) skip_smoke=true ;;
    -h|--help) printf 'Usage: %s [--rebuild] [--no-smoke]\n' "$0"; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$argument" >&2; exit 2 ;;
  esac
done

step() { printf '\n>>> %s\n' "$1"; }
ok() { printf '[OK] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1" >&2; exit 1; }

step 'Checking prerequisites'
command -v docker >/dev/null 2>&1 || fail 'Docker CLI was not found in PATH.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 is required.'
docker info >/dev/null 2>&1 || fail 'Docker daemon is not running. Start it and retry.'
ok 'Docker CLI, Compose, and daemon are available'

step 'Checking environment configuration'
if [[ ! -f .env ]]; then
  command -v openssl >/dev/null 2>&1 || fail 'openssl is required to securely generate .env.'
  password="$(openssl rand -base64 36 | tr -dc 'A-Za-z0-9' | head -c 24)"
  session_secret="$(openssl rand -hex 32)"
  umask 077
  {
    printf 'POSTGRES_DB=appdb\nPOSTGRES_USER=appuser\nPOSTGRES_PASSWORD=%s\n' "$password"
    printf 'API_PORT=8080\nAPI_BIND_ADDRESS=127.0.0.1\n'
    printf 'AUTH_MODE=ldap\nSESSION_SECRET=%s\nSESSION_TTL_SECONDS=3600\nSESSION_COOKIE_SECURE=true\n' "$session_secret"
  } > .env
  ok 'Generated .env with secure credentials'
else
  ok '.env already exists'
fi

step 'Validating Docker Compose configuration'
docker compose config >/dev/null || fail 'docker-compose.yml validation failed.'
ok 'docker-compose.yml is valid'

step 'Building API image'
build_args=(compose build api)
[[ "$force_rebuild" == true ]] && build_args+=(--no-cache)
docker "${build_args[@]}" || fail 'Docker build failed.'
ok 'API image built'

step 'Starting services'
docker compose up -d || fail 'Failed to start services.'
ok 'Services started'

step 'Waiting for service health checks'
healthy=false
for elapsed in $(seq 5 5 120); do
  sleep 5
  db_health="$(docker inspect --format='{{.State.Health.Status}}' app-db 2>/dev/null || true)"
  api_health="$(docker inspect --format='{{.State.Health.Status}}' app-api 2>/dev/null || true)"
  if [[ "$db_health" == healthy && "$api_health" == healthy ]]; then healthy=true; break; fi
  printf '  [%ss/120s] db=%s api=%s\n' "$elapsed" "${db_health:-starting}" "${api_health:-starting}"
done
[[ "$healthy" == true ]] || { docker compose logs --tail=20 api; fail 'Services did not become healthy in 120 seconds.'; }
ok 'All services are healthy'
docker compose ps

api_port="$(sed -nE 's/^API_PORT=([0-9]+)$/\1/p' .env | head -n 1)"
api_port="${api_port:-8080}"

if [[ "$skip_smoke" == false ]]; then
  step 'Running smoke test'
  curl --fail --silent --show-error --max-time 10 "http://localhost:${api_port}/health" | grep -q '"status":"ok"' || fail 'Health check failed.'
  ok 'Health check passed'
else
  printf '[SKIP] Smoke test skipped by flag.\n'
fi

printf '\nDeployment complete\nAPI: http://localhost:%s\nAPI docs: http://localhost:%s/docs\n' "$api_port" "$api_port"
