#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
assume_yes=false
dry_run=false

forward_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      forward_args+=(--env-file "$2")
      shift 2
      ;;
    --yes)
      assume_yes=true
      forward_args+=(--yes)
      shift
      ;;
    --dry-run)
      dry_run=true
      forward_args+=(--dry-run)
      shift
      ;;
    -h|--help)
      exec "${SCRIPT_DIR}/cli.sh" --help
      ;;
    *)
      vd_die "Unknown setup option: $1" 64
      ;;
  esac
done

vd_heading "VedicSign Production Setup"
bootstrap_args=(--ensure)
[[ "${assume_yes}" == true ]] && bootstrap_args+=(--yes)
[[ "${dry_run}" == true ]] && bootstrap_args+=(--dry-run)
"${SCRIPT_DIR}/bootstrap.sh" "${bootstrap_args[@]}"
"${SCRIPT_DIR}/configure.sh" "${forward_args[@]}"

if [[ "${dry_run}" == true && ! -f "${env_file}" ]]; then
  vd_warn "Dry run completed without writing ${env_file}; doctor will run after configuration exists."
  exit 0
fi

vd_heading "Configuration Doctor"
"${SCRIPT_DIR}/doctor.sh" --env-file "${env_file}" --scope config
bootstrap_path_args=(--ensure --prepare-paths --env-file "${env_file}")
[[ "${assume_yes}" == true ]] && bootstrap_path_args+=(--yes)
[[ "${dry_run}" == true ]] && bootstrap_path_args+=(--dry-run)
"${SCRIPT_DIR}/bootstrap.sh" "${bootstrap_path_args[@]}"

release_args=(--env-file "${env_file}" --no-pull)
[[ "${assume_yes}" == true ]] && release_args+=(--yes)
[[ "${dry_run}" == true ]] && release_args+=(--dry-run)
"${SCRIPT_DIR}/release.sh" "${release_args[@]}"
