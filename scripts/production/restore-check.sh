#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
archive=""
output_json=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    --archive)
      [[ $# -ge 2 ]] || vd_die "--archive requires a path" 64
      archive="$2"
      shift 2
      ;;
    --json) output_json=true; shift ;;
    -h|--help)
      printf 'Usage: ./deploy.sh restore-check [--env-file <path>] [--archive <tar.gz>] [--json]\n'
      exit 0
      ;;
    *) vd_die "Unknown restore-check option: $1" 64 ;;
  esac
done

[[ -f "${env_file}" ]] || vd_die "Environment file is missing: ${env_file}" 65
backup_dir="$(vd_env_value "${env_file}" BACKUP_DIR 2>/dev/null || true)"
[[ "${backup_dir}" == /* ]] || vd_die "BACKUP_DIR must be absolute" 65

if [[ -z "${archive}" ]]; then
  archive="$(find "${backup_dir}" -maxdepth 1 -type f -name 'sessions-*.tar.gz' \
    -print 2>/dev/null | sort | tail -n 1)"
fi
[[ -n "${archive}" && -f "${archive}" ]] || vd_die "No artifact backup archive was found" 66

unsafe_entry="$(tar -tzf "${archive}" | awk '
  /^\// || /(^|\/)\.\.($|\/)/ { print; exit }
')"
[[ -z "${unsafe_entry}" ]] || vd_die "Backup contains an unsafe path: ${unsafe_entry}" 66

restore_root="$(mktemp -d "${TMPDIR:-/tmp}/vedicsign-restore-check.XXXXXX")"
trap 'rm -rf "${restore_root}"' EXIT
tar -xzf "${archive}" -C "${restore_root}"
file_count="$(find "${restore_root}" -type f | wc -l | tr -d ' ')"

if [[ "${output_json}" == true ]]; then
  printf '{"ok":true,"archive":"%s","files":%s}\n' \
    "$(vd_json_escape "${archive}")" "${file_count}"
else
  vd_ok "Backup restore check passed: ${archive} (${file_count} files)"
  vd_info "Validation used an isolated temporary directory and did not change production data."
fi
