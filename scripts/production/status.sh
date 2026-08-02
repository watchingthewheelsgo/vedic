#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

output_json=false
env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) output_json=true; shift ;;
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    -h|--help)
      printf 'Usage: ./deploy.sh status [--env-file <path>] [--json]\n'
      exit 0
      ;;
    *) vd_die "Unknown status option: $1" 64 ;;
  esac
done

sha="$(vd_git_sha)"
site_domain="$(vd_env_value "${env_file}" SITE_DOMAIN 2>/dev/null || true)"
api_domain="$(vd_env_value "${env_file}" API_DOMAIN 2>/dev/null || true)"
config_state="missing"
[[ -f "${env_file}" ]] && config_state="present"
runtime_state="not-configured"
current_release=""
previous_release=""
[[ -f "${VEDICSIGN_ROOT}/.deploy/current-release" ]] \
  && current_release="$(vd_trim "$(<"${VEDICSIGN_ROOT}/.deploy/current-release")")"
[[ -f "${VEDICSIGN_ROOT}/.deploy/previous-release" ]] \
  && previous_release="$(vd_trim "$(<"${VEDICSIGN_ROOT}/.deploy/previous-release")")"

if [[ -f "${VEDICSIGN_ROOT}/compose.production.yml" ]] && vd_has_command docker; then
  runtime_state="stopped"
  if VEDICSIGN_ENV_FILE="${env_file}" \
    docker compose --env-file "${env_file}" -f "${VEDICSIGN_ROOT}/compose.production.yml" \
      ps --status running --quiet 2>/dev/null | grep -q .; then
    runtime_state="running"
  fi
fi

if [[ "${output_json}" == true ]]; then
  printf '{"sourceSha":"%s","configuration":"%s","runtime":"%s","currentRelease":"%s","previousRelease":"%s","webOrigin":"%s","apiOrigin":"%s"}\n' \
    "$(vd_json_escape "${sha}")" "${config_state}" "${runtime_state}" \
    "$(vd_json_escape "${current_release}")" "$(vd_json_escape "${previous_release}")" \
    "$(vd_json_escape "$([[ -n "${site_domain}" ]] && printf 'https://%s' "${site_domain}")")" \
    "$(vd_json_escape "$([[ -n "${api_domain}" ]] && printf 'https://%s' "${api_domain}")")"
  exit 0
fi

vd_heading "VedicSign Deployment Status"
vd_info "Source: ${sha}"
vd_info "Configuration: ${config_state}"
vd_info "Runtime: ${runtime_state}"
[[ -n "${current_release}" ]] && vd_info "Current release: ${current_release}"
[[ -n "${previous_release}" ]] && vd_info "Rollback target: ${previous_release}"
[[ -n "${site_domain}" ]] && vd_info "Web: https://${site_domain}"
[[ -n "${api_domain}" ]] && vd_info "API: https://${api_domain}"
