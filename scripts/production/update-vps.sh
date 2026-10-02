#!/usr/bin/env bash
# Run on the VPS from a clean checkout. Configuration stays outside Git.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
[[ -f .env.production ]] || { echo 'Missing .env.production' >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Refusing to overwrite a dirty checkout' >&2; exit 1; }
mkdir -p .deploy/backups
exec 9>.deploy/vps.lock
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
mode="${1:-update}"
[[ "$mode" == update || "$mode" == --no-pull || "$mode" == --rollback ]] || exit 64
docker_cmd=(docker)
docker info >/dev/null 2>&1 || docker_cmd=(sudo -n docker)
compose() { "${docker_cmd[@]}" compose --env-file .env.production -f compose.vps.yml "$@"; }
old_tag="$(cat .deploy/vps-current 2>/dev/null || true)"
if [[ "$mode" == --rollback ]]; then
  export VEDICSIGN_IMAGE_TAG="$(cat .deploy/vps-previous)"
  compose up -d --no-build --wait --wait-timeout 240
  printf '%s\n' "$VEDICSIGN_IMAGE_TAG" > .deploy/vps-current
  printf '%s\n' "$old_tag" > .deploy/vps-previous
  echo "Application rolled back to $VEDICSIGN_IMAGE_TAG; database schema unchanged."
  exit 0
fi
if [[ "$mode" == update ]]; then
  git fetch origin main
  git merge --ff-only origin/main
  # Execute the updated script, holding the same inherited lock only until exec.
  flock -u 9
  exec bash scripts/production/update-vps.sh --no-pull
fi
export VEDICSIGN_IMAGE_TAG="$(git rev-parse --short=12 HEAD)"
export COMPOSE_PARALLEL_LIMIT=1
compose config --quiet
bash scripts/production/doctor.sh --scope config --env-file "$PWD/.env.production"
# Build sequentially to fit a small VPS. No running service changes on build failure.
compose build backend
compose build web
compose up -d --wait --wait-timeout 120 db
umask 077
backup=".deploy/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup"
compose exec -T db pg_dump -U signatlas -d signatlas -Fc > "$backup/database.dump"
source scripts/production/lib/common.sh
session_dir="$(vd_env_value "$PWD/.env.production" SESSION_DATA_DIR)"
tar -czf "$backup/sessions.tar.gz" -C "$session_dir" .
compose run --rm --no-deps backend python scripts/production/run-migrations.py
verify() {
  curl -fsS --max-time 15 http://127.0.0.1:18880/ >/dev/null || return 1
  curl -fsS --max-time 15 http://127.0.0.1:18787/api/health | python3 -c 'import json,sys; assert json.load(sys.stdin)["ok"] is True' || return 1
  curl -fsS --max-time 20 https://signatlas.app/ >/dev/null || return 1
  curl -fsS --max-time 20 https://api.signatlas.app/health | python3 -c 'import json,sys; assert json.load(sys.stdin)["ok"] is True' || return 1
  curl -fsS --max-time 20 -X OPTIONS https://api.signatlas.app/v1/me \
    -H 'Origin: https://signatlas.app' -H 'Access-Control-Request-Method: GET' \
    -H 'Access-Control-Request-Headers: authorization' \
    -D - -o /dev/null | tr -d '\r' | grep -qi '^access-control-allow-origin: https://signatlas.app$'
}
if ! compose up -d --no-build --wait --wait-timeout 240 backend web || ! verify; then
  if [[ -n "$old_tag" ]]; then
    export VEDICSIGN_IMAGE_TAG="$old_tag"
    compose up -d --no-build --wait --wait-timeout 240 backend web
  else
    compose stop backend web
  fi
  echo 'Release failed; database migrations were not reversed.' >&2
  exit 1
fi
if [[ -n "$old_tag" && "$old_tag" != "$VEDICSIGN_IMAGE_TAG" ]]; then
  printf '%s\n' "$old_tag" > .deploy/vps-previous
fi
printf '%s\n' "$VEDICSIGN_IMAGE_TAG" > .deploy/vps-current
echo "Deployed $VEDICSIGN_IMAGE_TAG; backup: $backup"
echo 'Clerk login and payment verification are separate acceptance checks.'
