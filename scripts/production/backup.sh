#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
output_json=false
dry_run=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    --json) output_json=true; shift ;;
    --dry-run) dry_run=true; shift ;;
    -h|--help)
      printf 'Usage: ./deploy.sh backup [--env-file <path>] [--dry-run] [--json]\n'
      exit 0
      ;;
    *) vd_die "Unknown backup option: $1" 64 ;;
  esac
done

[[ -f "${env_file}" ]] || vd_die "Environment file is missing: ${env_file}" 65
session_data_dir="$(vd_env_value "${env_file}" SESSION_DATA_DIR 2>/dev/null || true)"
backup_dir="$(vd_env_value "${env_file}" BACKUP_DIR 2>/dev/null || true)"
[[ "${session_data_dir}" == /* && "${backup_dir}" == /* ]] \
  || vd_die "SESSION_DATA_DIR and BACKUP_DIR must be absolute" 65

timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
archive="${backup_dir}/sessions-${timestamp}.tar.gz"

if [[ "${dry_run}" == true ]]; then
  if [[ "${output_json}" == true ]]; then
    printf '{"ok":true,"dryRun":true,"source":"%s","archive":"%s"}\n' \
      "$(vd_json_escape "${session_data_dir}")" "$(vd_json_escape "${archive}")"
  else
    vd_info "Dry run: would archive ${session_data_dir} to ${archive}"
  fi
  exit 0
fi

[[ -d "${session_data_dir}" ]] || vd_die "Session data directory does not exist: ${session_data_dir}" 66
mkdir -p "${backup_dir}"
tar -C "${session_data_dir}" -czf "${archive}" .

if [[ "${output_json}" == true ]]; then
  printf '{"ok":true,"archive":"%s"}\n' "$(vd_json_escape "${archive}")"
else
  vd_ok "Artifact backup created: ${archive}"
  vd_warn "This archive does not back up managed PostgreSQL; verify provider backups separately."
fi
