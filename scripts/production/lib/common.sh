#!/usr/bin/env bash

if [[ -n "${VEDICSIGN_COMMON_LOADED:-}" ]]; then
  return 0
fi
readonly VEDICSIGN_COMMON_LOADED=1

VEDICSIGN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VEDICSIGN_DEFAULT_ENV_FILE="${VEDICSIGN_ROOT}/.env.production"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  VEDICSIGN_BOLD=$'\033[1m'
  VEDICSIGN_DIM=$'\033[2m'
  VEDICSIGN_GREEN=$'\033[32m'
  VEDICSIGN_YELLOW=$'\033[33m'
  VEDICSIGN_RED=$'\033[31m'
  VEDICSIGN_CYAN=$'\033[36m'
  VEDICSIGN_RESET=$'\033[0m'
else
  VEDICSIGN_BOLD=""
  VEDICSIGN_DIM=""
  VEDICSIGN_GREEN=""
  VEDICSIGN_YELLOW=""
  VEDICSIGN_RED=""
  VEDICSIGN_CYAN=""
  VEDICSIGN_RESET=""
fi

vd_heading() {
  printf '\n%s%s%s\n' "${VEDICSIGN_BOLD}" "$1" "${VEDICSIGN_RESET}"
}

vd_info() {
  printf '%s●%s %s\n' "${VEDICSIGN_CYAN}" "${VEDICSIGN_RESET}" "$1"
}

vd_ok() {
  printf '%s✓%s %s\n' "${VEDICSIGN_GREEN}" "${VEDICSIGN_RESET}" "$1"
}

vd_warn() {
  printf '%s!%s %s\n' "${VEDICSIGN_YELLOW}" "${VEDICSIGN_RESET}" "$1" >&2
}

vd_error() {
  printf '%s✗%s %s\n' "${VEDICSIGN_RED}" "${VEDICSIGN_RESET}" "$1" >&2
}

vd_die() {
  vd_error "$1"
  exit "${2:-1}"
}

vd_has_command() {
  command -v "$1" >/dev/null 2>&1
}

vd_trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

# Read a dotenv value without sourcing or evaluating the file.
vd_env_value() {
  local file="$1"
  local wanted_key="$2"
  local raw_line key value first last

  [[ -f "${file}" ]] || return 1
  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    raw_line="${raw_line%$'\r'}"
    [[ -z "${raw_line}" || "${raw_line}" == \#* || "${raw_line}" != *=* ]] && continue
    key="$(vd_trim "${raw_line%%=*}")"
    [[ "${key}" == "${wanted_key}" ]] || continue
    value="$(vd_trim "${raw_line#*=}")"
    if [[ ${#value} -ge 2 ]]; then
      first="${value:0:1}"
      last="${value: -1}"
      if [[ ( "${first}" == '"' && "${last}" == '"' ) || ( "${first}" == "'" && "${last}" == "'" ) ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi
    printf '%s' "${value}"
    return 0
  done < "${file}"
  return 1
}

vd_is_placeholder() {
  local value
  value="$(vd_trim "${1:-}")"
  [[ -z "${value}" || "${value}" == *'<'* || "${value}" == *'>'* || "${value}" == *'...'*
    || "${value}" == *'USER:PASSWORD'* ]]
}

vd_is_domain() {
  [[ "$1" =~ ^([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]
}

vd_json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "${value}"
}

vd_file_mode() {
  local path="$1"
  if stat -c '%a' "${path}" >/dev/null 2>&1; then
    stat -c '%a' "${path}"
  else
    stat -f '%Lp' "${path}"
  fi
}

vd_git_sha() {
  git -C "${VEDICSIGN_ROOT}" rev-parse --short=12 HEAD 2>/dev/null || printf 'unknown'
}
