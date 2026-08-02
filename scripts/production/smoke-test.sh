#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
output_json=false
local_only=false
attempts=12

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    --json) output_json=true; shift ;;
    --local-only) local_only=true; shift ;;
    --attempts)
      [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]] || vd_die "--attempts requires a number" 64
      attempts="$2"
      shift 2
      ;;
    -h|--help)
      printf 'Usage: smoke-test.sh [--env-file <path>] [--local-only] [--attempts <n>] [--json]\n'
      exit 0
      ;;
    *) vd_die "Unknown smoke-test option: $1" 64 ;;
  esac
done

[[ -f "${env_file}" ]] || vd_die "Environment file is missing: ${env_file}" 65
site_domain="$(vd_env_value "${env_file}" SITE_DOMAIN 2>/dev/null || true)"
api_domain="$(vd_env_value "${env_file}" API_DOMAIN 2>/dev/null || true)"
[[ -n "${site_domain}" && -n "${api_domain}" ]] || vd_die "SITE_DOMAIN and API_DOMAIN are required" 65
vd_has_command curl || vd_die "curl is required for smoke tests" 69

export VEDICSIGN_ENV_FILE="${env_file}"
compose=(docker compose --env-file "${env_file}" -f "${VEDICSIGN_ROOT}/compose.production.yml")

backend_response="$("${compose[@]}" exec -T backend python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=8).read().decode())" \
  2>/dev/null || true)"
[[ "${backend_response}" == *'"ok":true'* || "${backend_response}" == *'"ok": true'* ]] \
  || vd_die "Backend container health check failed" 70

if [[ "${local_only}" == true ]]; then
  if [[ "${output_json}" == true ]]; then
    printf '{"ok":true,"localOnly":true}\n'
  else
    vd_ok "Backend container health check passed"
  fi
  exit 0
fi

web_url="https://${site_domain}/"
api_url="https://${api_domain}/health"

wait_for_url() {
  local url="$1" attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if curl --fail --silent --show-error --location --max-time 15 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}

wait_for_url "${web_url}" || vd_die "Web smoke test failed: ${web_url}" 70
wait_for_url "${api_url}" || vd_die "API smoke test failed: ${api_url}" 70
api_response="$(curl --fail --silent --show-error --max-time 15 "${api_url}")" \
  || vd_die "API smoke test failed: ${api_url}" 70
[[ "${api_response}" == *'"ok":true'* || "${api_response}" == *'"ok": true'* ]] \
  || vd_die "API health response is not healthy" 70

cors_headers="$(curl --silent --show-error --max-time 15 -X OPTIONS \
  -H "Origin: https://${site_domain}" \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,x-vedic-anonymous-id' \
  -D - -o /dev/null "https://${api_domain}/v1/me")" \
  || vd_die "Production CORS preflight request failed" 70
printf '%s' "${cors_headers}" | tr -d '\r' \
  | grep -qi "^access-control-allow-origin: https://${site_domain}$" \
  || vd_die "Production CORS preflight did not allow the canonical Web origin" 70

if [[ "${output_json}" == true ]]; then
  printf '{"ok":true,"web":"%s","api":"%s","cors":true}\n' \
    "$(vd_json_escape "${web_url}")" "$(vd_json_escape "${api_url}")"
else
  vd_ok "Web smoke test passed: ${web_url}"
  vd_ok "API smoke test passed: ${api_url}"
  vd_ok "Production CORS preflight passed"
fi
