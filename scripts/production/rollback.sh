#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
output_json=false
assume_yes=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    --json) output_json=true; shift ;;
    --yes) assume_yes=true; shift ;;
    -h|--help)
      printf 'Usage: ./deploy.sh rollback [--env-file <path>] [--yes] [--json]\n'
      exit 0
      ;;
    *) vd_die "Unknown rollback option: $1" 64 ;;
  esac
done


state_dir="${VEDICSIGN_ROOT}/.deploy"
current_file="${state_dir}/current-release"
previous_file="${state_dir}/previous-release"
if [[ ! -f "${previous_file}" ]]; then
  if [[ "${output_json}" == true ]]; then
    printf '{"ok":false,"code":"ROLLBACK_NOT_AVAILABLE","message":"No previous release is available"}\n'
    exit 69
  fi
  vd_die "No previous release is available" 69
fi
[[ -f "${env_file}" ]] || vd_die "Environment file is missing: ${env_file}" 65

current_tag="$(vd_trim "$(<"${current_file}")")"
previous_tag="$(vd_trim "$(<"${previous_file}")")"
[[ -n "${previous_tag}" ]] || vd_die "Previous release state is empty" 69

if [[ "${assume_yes}" == false ]]; then
  vd_warn "This rolls application images back from ${current_tag:-unknown} to ${previous_tag}."
  vd_warn "Database migrations are not downgraded automatically."
  read -r -p "Continue with application rollback? (y/N): " answer
  [[ "${answer}" == [Yy]* ]] || vd_die "Rollback cancelled" 75
fi

export VEDICSIGN_IMAGE_TAG="${previous_tag}"
export VEDICSIGN_ENV_FILE="${env_file}"
compose=(docker compose --env-file "${env_file}" -f "${VEDICSIGN_ROOT}/compose.production.yml")
"${compose[@]}" up -d --remove-orphans
"${SCRIPT_DIR}/smoke-test.sh" --env-file "${env_file}" --attempts 18

printf '%s\n' "${current_tag}" > "${previous_file}"
printf '%s\n' "${previous_tag}" > "${current_file}"

if [[ "${output_json}" == true ]]; then
  printf '{"ok":true,"release":"%s","previous":"%s"}\n' \
    "$(vd_json_escape "${previous_tag}")" "$(vd_json_escape "${current_tag}")"
else
  vd_ok "Application rollback complete: ${previous_tag}"
fi
