#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
dry_run=false
assume_yes=false
output_json=false
pull_source=true
release_ref="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    --dry-run) dry_run=true; shift ;;
    --json) output_json=true; shift ;;
    --yes) assume_yes=true; shift ;;
    --no-pull) pull_source=false; shift ;;
    --ref)
      [[ $# -ge 2 ]] || vd_die "--ref requires a Git ref" 64
      release_ref="$2"
      shift 2
      ;;
    -h|--help)
      printf 'Usage: ./deploy.sh [--env-file <path>] [--ref <git-ref>] [--no-pull] [--dry-run] [--yes] [--json]\n'
      exit 0
      ;;
    *) vd_die "Unknown deploy option: $1" 64 ;;
  esac
done

[[ -f "${env_file}" ]] || vd_die "Environment file is missing: ${env_file}; run ./deploy.sh setup" 65

site_domain="$(vd_env_value "${env_file}" SITE_DOMAIN 2>/dev/null || true)"
api_domain="$(vd_env_value "${env_file}" API_DOMAIN 2>/dev/null || true)"
state_dir="${VEDICSIGN_ROOT}/.deploy"
logs_dir="${state_dir}/logs"
lock_dir="${state_dir}/release.lock"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
log_file="${logs_dir}/release-${timestamp}.log"
current_file="${state_dir}/current-release"
previous_file="${state_dir}/previous-release"
cleanup_lock() {
  rmdir "${lock_dir}" 2>/dev/null || true
}

run_logged() {
  local label="$1"
  shift
  local started
  started="$(date +%s)"
  [[ "${output_json}" == true ]] || vd_info "${label}..."
  if "$@" >> "${log_file}" 2>&1; then
    [[ "${output_json}" == true ]] || vd_ok "${label} ($(( $(date +%s) - started ))s)"
    return 0
  fi
  vd_error "${label} failed; see ${log_file}"
  tail -n 30 "${log_file}" >&2 || true
  return 1
}

compose() {
  VEDICSIGN_ENV_FILE="${env_file}" \
    docker compose --env-file "${env_file}" -f "${VEDICSIGN_ROOT}/compose.production.yml" "$@"
}

vd_heading "VedicSign Release Plan"
vd_info "Requested ref: ${release_ref}"
vd_info "Current source: $(vd_git_sha)"
vd_info "Web: https://${site_domain}"
vd_info "API: https://${api_domain}"
vd_info "Configuration: ${env_file}"
[[ "${pull_source}" == true ]] && vd_info "Source update: git fetch + fast-forward"
[[ "${pull_source}" == false ]] && vd_info "Source update: disabled for first deployment"
[[ "${dry_run}" == true ]] && vd_info "Mode: dry run"

"${SCRIPT_DIR}/doctor.sh" --env-file "${env_file}" --scope config

if [[ "${dry_run}" == true ]]; then
  vd_heading "Repository Readiness"
  "${SCRIPT_DIR}/doctor.sh" --env-file "${env_file}" --scope all
  vd_info "Dry run complete; Git, images, database, and services were not changed."
  exit 0
fi

mkdir -p "${logs_dir}"
if ! mkdir "${lock_dir}" 2>/dev/null; then
  vd_die "Another VedicSign release appears to be running (${lock_dir})" 73
fi
trap cleanup_lock EXIT

if [[ "${assume_yes}" == false ]]; then
  read -r -p "Build and deploy this release? (Y/n): " answer
  [[ -z "${answer}" || "${answer}" == [Yy]* ]] || vd_die "Release cancelled" 75
fi

if [[ -n "$(git -C "${VEDICSIGN_ROOT}" status --porcelain)" ]]; then
  vd_die "The VPS checkout has local changes. Commit/remove them before deployment; deploy.sh will not overwrite them." 65
fi

before_sha="$(git -C "${VEDICSIGN_ROOT}" rev-parse HEAD)"
if [[ "${pull_source}" == true ]]; then
  run_logged "Fetch ${release_ref}" git -C "${VEDICSIGN_ROOT}" fetch --prune origin "${release_ref}"
  if git -C "${VEDICSIGN_ROOT}" show-ref --verify --quiet "refs/remotes/origin/${release_ref}"; then
    run_logged "Fast-forward source" git -C "${VEDICSIGN_ROOT}" merge --ff-only "origin/${release_ref}"
  else
    run_logged "Checkout fetched release" git -C "${VEDICSIGN_ROOT}" checkout --detach FETCH_HEAD
  fi
fi

release_sha="$(git -C "${VEDICSIGN_ROOT}" rev-parse HEAD)"
release_tag="$(git -C "${VEDICSIGN_ROOT}" rev-parse --short=12 HEAD)"
build_time="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
export VEDICSIGN_IMAGE_TAG="${release_tag}"
export VEDICSIGN_GIT_SHA="${release_sha}"
export VEDICSIGN_BUILD_TIME="${build_time}"
export VEDICSIGN_ENV_FILE="${env_file}"
export VITE_API_BASE_URL="$(vd_env_value "${env_file}" VITE_API_BASE_URL)"
export VITE_CLERK_PUBLISHABLE_KEY="$(vd_env_value "${env_file}" VITE_CLERK_PUBLISHABLE_KEY)"

"${SCRIPT_DIR}/doctor.sh" --env-file "${env_file}" --scope all
run_logged "Validate Compose configuration" compose config --quiet
run_logged "Build backend and Web images" compose build --pull

previous_tag=""
[[ -f "${current_file}" ]] && previous_tag="$(vd_trim "$(<"${current_file}")")"

session_data_dir="$(vd_env_value "${env_file}" SESSION_DATA_DIR)"
if [[ -d "${session_data_dir}" ]] && find "${session_data_dir}" -mindepth 1 -print -quit | grep -q .; then
  run_logged "Back up session artifacts" "${SCRIPT_DIR}/backup.sh" --env-file "${env_file}"
fi

if [[ -f "${VEDICSIGN_ROOT}/backend/alembic.ini" && -d "${VEDICSIGN_ROOT}/backend/alembic" ]]; then
  vd_warn "Database migrations are forward-only during automatic application rollback."
  run_logged "Apply database migrations" compose run --rm --no-deps backend \
    alembic -c backend/alembic.ini upgrade head
fi

new_runtime_started=false
if run_logged "Start release ${release_tag}" compose up -d --remove-orphans; then
  new_runtime_started=true
else
  new_runtime_started=true
fi

release_ok=true
run_logged "Verify container health" "${SCRIPT_DIR}/smoke-test.sh" \
  --env-file "${env_file}" --local-only --attempts 18 || release_ok=false
if [[ "${release_ok}" == true ]]; then
  run_logged "Verify public Web, API, and CORS" "${SCRIPT_DIR}/smoke-test.sh" \
    --env-file "${env_file}" --attempts 18 || release_ok=false
fi

if [[ "${release_ok}" != true ]]; then
  vd_error "Release ${release_tag} failed verification."
  if [[ -n "${previous_tag}" ]]; then
    export VEDICSIGN_IMAGE_TAG="${previous_tag}"
    run_logged "Restore previous image ${previous_tag}" compose up -d --remove-orphans \
      || vd_error "Automatic application rollback failed; manual intervention is required"
  elif [[ "${new_runtime_started}" == true ]]; then
    run_logged "Stop failed first release" compose down \
      || vd_error "Could not stop the failed first release"
  fi
  vd_warn "Database migrations were not automatically downgraded."
  exit 70
fi

if [[ -n "${previous_tag}" && "${previous_tag}" != "${release_tag}" ]]; then
  printf '%s\n' "${previous_tag}" > "${previous_file}"
fi
printf '%s\n' "${release_tag}" > "${current_file}"
printf '%s\n' "${release_sha}" > "${state_dir}/current-sha"

if [[ "${output_json}" == true ]]; then
  printf '{"ok":true,"release":"%s","sha":"%s","previous":"%s","web":"https://%s","api":"https://%s","log":"%s"}\n' \
    "$(vd_json_escape "${release_tag}")" "$(vd_json_escape "${release_sha}")" \
    "$(vd_json_escape "${previous_tag}")" "$(vd_json_escape "${site_domain}")" \
    "$(vd_json_escape "${api_domain}")" "$(vd_json_escape "${log_file}")"
else
  vd_heading "Release Complete"
  vd_ok "Release: ${release_tag} (${release_sha})"
  vd_ok "Web: https://${site_domain}"
  vd_ok "API: https://${api_domain}"
  [[ -n "${previous_tag}" ]] && vd_info "Rollback target: ${previous_tag}"
  vd_info "Log: ${log_file}"
  [[ "${before_sha}" != "${release_sha}" ]] && vd_info "Source updated from ${before_sha:0:12}"
fi
