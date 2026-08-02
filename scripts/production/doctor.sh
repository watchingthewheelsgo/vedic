#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
output_json=false
scope="all"

usage() {
  cat <<'EOF'
Usage: ./deploy.sh doctor [--env-file <path>] [--scope config|all] [--json]

Runs read-only configuration and repository release-readiness checks.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    --scope)
      [[ $# -ge 2 ]] || vd_die "--scope requires config or all" 64
      scope="$2"
      shift 2
      ;;
    --json)
      output_json=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      vd_die "Unknown doctor option: $1" 64
      ;;
  esac
done

[[ "${scope}" == "config" || "${scope}" == "all" ]] || vd_die "Invalid scope: ${scope}" 64

result_levels=()
result_codes=()
result_messages=()
passed=0
warnings=0
blockers=0

add_result() {
  local level="$1" code="$2" message="$3"
  result_levels+=("${level}")
  result_codes+=("${code}")
  result_messages+=("${message}")
  case "${level}" in
    pass) passed=$((passed + 1)) ;;
    warning) warnings=$((warnings + 1)) ;;
    blocker) blockers=$((blockers + 1)) ;;
  esac
}

require_env() {
  local key="$1" code="$2" description="$3" value
  value="$(vd_env_value "${env_file}" "${key}" 2>/dev/null || true)"
  if vd_is_placeholder "${value}"; then
    add_result blocker "${code}" "${description} is missing (${key})"
  else
    add_result pass "${code}" "${description} is configured"
  fi
}

check_configuration() {
  local mode app_env site_domain api_domain allowed_origins api_base auth_mode reload_value
  local database_url agent_base_url ai_mode creem_test_mode creem_success_url file_mode
  local runtime_uid runtime_gid session_data_dir backup_dir

  if [[ ! -f "${env_file}" ]]; then
    add_result blocker ENV_FILE_MISSING "Production environment file does not exist: ${env_file}"
    return
  fi

  add_result pass ENV_FILE_PRESENT "Production environment file exists"
  file_mode="$(vd_file_mode "${env_file}")"
  if [[ "${file_mode}" == "600" || "${file_mode}" == "400" ]]; then
    add_result pass ENV_FILE_MODE "Environment file permissions are ${file_mode}"
  else
    add_result blocker ENV_FILE_MODE "Environment file permissions are ${file_mode}; expected 600 or 400"
  fi

  app_env="$(vd_env_value "${env_file}" APP_ENV 2>/dev/null || true)"
  [[ "${app_env}" == "production" ]] \
    && add_result pass APP_ENV "APP_ENV is production" \
    || add_result blocker APP_ENV "APP_ENV must be production"

  site_domain="$(vd_env_value "${env_file}" SITE_DOMAIN 2>/dev/null || true)"
  if vd_is_domain "${site_domain}"; then
    add_result pass SITE_DOMAIN "Web domain is valid: ${site_domain}"
  else
    add_result blocker SITE_DOMAIN "SITE_DOMAIN is missing or invalid"
  fi

  api_domain="$(vd_env_value "${env_file}" API_DOMAIN 2>/dev/null || true)"
  if vd_is_domain "${api_domain}" && [[ "${api_domain}" == "api.${site_domain}" ]]; then
    add_result pass API_DOMAIN "API domain matches the Web domain"
  else
    add_result blocker API_DOMAIN "API_DOMAIN must be api.${site_domain:-<site-domain>}"
  fi

  allowed_origins="$(vd_env_value "${env_file}" ALLOWED_ORIGINS 2>/dev/null || true)"
  if [[ "${allowed_origins}" == "https://${site_domain}" ]]; then
    add_result pass ALLOWED_ORIGINS "CORS origin is restricted to the Web origin"
  else
    add_result blocker ALLOWED_ORIGINS "ALLOWED_ORIGINS must equal https://${site_domain:-<site-domain>}"
  fi

  api_base="$(vd_env_value "${env_file}" VITE_API_BASE_URL 2>/dev/null || true)"
  if [[ "${api_base}" == "https://${api_domain}/v1" ]]; then
    add_result pass VITE_API_BASE_URL "Frontend API base URL matches the API domain"
  else
    add_result blocker VITE_API_BASE_URL "VITE_API_BASE_URL must equal https://${api_domain:-<api-domain>}/v1"
  fi

  auth_mode="$(vd_env_value "${env_file}" VEDIC_AUTH_MODE 2>/dev/null || true)"
  [[ "${auth_mode}" == "clerk" ]] \
    && add_result pass AUTH_MODE "Clerk authentication is enabled" \
    || add_result blocker AUTH_MODE "VEDIC_AUTH_MODE must be clerk"
  require_env VITE_CLERK_PUBLISHABLE_KEY CLERK_PUBLISHABLE_KEY "Clerk publishable key"
  require_env CLERK_SECRET_KEY CLERK_SECRET_KEY "Clerk secret key"

  database_url="$(vd_env_value "${env_file}" DATABASE_URL 2>/dev/null || true)"
  if [[ "${database_url}" == postgresql://* || "${database_url}" == postgres://* ]]; then
    add_result pass DATABASE_URL "PostgreSQL URL is configured"
  else
    add_result blocker DATABASE_URL "DATABASE_URL must use PostgreSQL in production"
  fi

  if ! vd_is_placeholder "$(vd_env_value "${env_file}" DEEPSEEK_API_KEY 2>/dev/null || true)" \
    || ! vd_is_placeholder "$(vd_env_value "${env_file}" ANTHROPIC_AUTH_TOKEN 2>/dev/null || true)" \
    || ! vd_is_placeholder "$(vd_env_value "${env_file}" ANTHROPIC_API_KEY 2>/dev/null || true)"; then
    add_result pass AGENT_TOKEN "Agent runtime token is configured"
  else
    add_result blocker AGENT_TOKEN "DEEPSEEK_API_KEY, ANTHROPIC_AUTH_TOKEN, or ANTHROPIC_API_KEY is required"
  fi
  require_env ANTHROPIC_MODEL AGENT_MODEL "Agent model"
  agent_base_url="$(vd_env_value "${env_file}" ANTHROPIC_BASE_URL 2>/dev/null || true)"
  [[ "${agent_base_url}" == https://* ]] \
    && add_result pass AGENT_BASE_URL "Agent base URL uses HTTPS" \
    || add_result blocker AGENT_BASE_URL "ANTHROPIC_BASE_URL must use HTTPS"
  ai_mode="$(vd_env_value "${env_file}" VEDIC_AI_MODE 2>/dev/null || true)"
  [[ "${ai_mode}" != "mock" ]] \
    && add_result pass AI_MODE "Agent runtime is not in mock mode" \
    || add_result blocker AI_MODE "VEDIC_AI_MODE cannot be mock in production"

  reload_value="$(vd_env_value "${env_file}" RELOAD 2>/dev/null || true)"
  [[ "${reload_value}" == "false" ]] \
    && add_result pass RELOAD_DISABLED "Backend reload is disabled" \
    || add_result blocker RELOAD_DISABLED "RELOAD must be false"

  runtime_uid="$(vd_env_value "${env_file}" VEDICSIGN_UID 2>/dev/null || true)"
  runtime_gid="$(vd_env_value "${env_file}" VEDICSIGN_GID 2>/dev/null || true)"
  if [[ "${runtime_uid}" =~ ^[0-9]+$ && "${runtime_gid}" =~ ^[0-9]+$ ]]; then
    add_result pass RUNTIME_IDS "Container UID/GID are configured"
  else
    add_result blocker RUNTIME_IDS "VEDICSIGN_UID and VEDICSIGN_GID must be numeric"
  fi
  session_data_dir="$(vd_env_value "${env_file}" SESSION_DATA_DIR 2>/dev/null || true)"
  backup_dir="$(vd_env_value "${env_file}" BACKUP_DIR 2>/dev/null || true)"
  [[ "${session_data_dir}" == /* ]] \
    && add_result pass SESSION_DATA_DIR "Session data path is absolute" \
    || add_result blocker SESSION_DATA_DIR "SESSION_DATA_DIR must be an absolute host path"
  [[ "${backup_dir}" == /* ]] \
    && add_result pass BACKUP_DIR "Backup path is absolute" \
    || add_result blocker BACKUP_DIR "BACKUP_DIR must be an absolute host path"

  creem_test_mode="$(vd_env_value "${env_file}" CREEM_TEST_MODE 2>/dev/null || true)"
  creem_success_url="$(vd_env_value "${env_file}" CREEM_SUCCESS_URL 2>/dev/null || true)"
  if [[ "${creem_success_url}" == "https://${site_domain}/account?billing=success" ]]; then
    add_result pass CREEM_SUCCESS_URL "Creem success URL matches the Web domain"
  else
    add_result blocker CREEM_SUCCESS_URL "CREEM_SUCCESS_URL must match the canonical Web account URL"
  fi
  if [[ "${creem_test_mode}" == "true" ]]; then
    add_result warning CREEM_TEST_MODE "Creem is in test mode; public production billing is not live"
  elif [[ "${creem_test_mode}" == "false" ]]; then
    require_env CREEM_API_KEY CREEM_API_KEY "Creem API key"
    require_env CREEM_WEBHOOK_SECRET CREEM_WEBHOOK_SECRET "Creem webhook secret"
    require_env CREEM_PRODUCT_PRO_MONTHLY CREEM_MONTHLY_PRODUCT "Creem monthly product"
  else
    add_result blocker CREEM_TEST_MODE "CREEM_TEST_MODE must be true or false"
  fi
}

check_repository() {
  local path
  for path in .dockerignore Dockerfile compose.production.yml deploy/Caddyfile \
    scripts/production/container-entrypoint.sh scripts/production/smoke-test.sh; do
    if [[ -f "${VEDICSIGN_ROOT}/${path}" ]]; then
      add_result pass "REPO_${path//[^A-Za-z0-9]/_}" "${path} exists"
    else
      add_result blocker "REPO_${path//[^A-Za-z0-9]/_}" "Required deployment artifact is missing: ${path}"
    fi
  done

  if [[ -f "${VEDICSIGN_ROOT}/backend/app/auth.py" ]] \
    && grep -q '"verify_signature": False' "${VEDICSIGN_ROOT}/backend/app/auth.py"; then
    add_result blocker AUTH_JWT_SIGNATURE "Clerk JWT signature verification is disabled in backend/app/auth.py"
  else
    add_result pass AUTH_JWT_SIGNATURE "No disabled JWT signature verifier was detected"
  fi

  if grep -Rqs 'VITE_API_BASE_URL' "${VEDICSIGN_ROOT}/src/client"; then
    add_result pass CLIENT_API_BASE "Frontend has production API base URL support"
  else
    add_result blocker CLIENT_API_BASE "Frontend still lacks VITE_API_BASE_URL support"
  fi

  if grep -Rqs 'ALLOWED_ORIGINS' "${VEDICSIGN_ROOT}/backend/app"; then
    add_result pass BACKEND_CORS_ENV "Backend CORS origins are environment-configurable"
  else
    add_result blocker BACKEND_CORS_ENV "Backend still lacks ALLOWED_ORIGINS support"
  fi

  if grep -q '"calculatorRoot"\|"skillsRoot"\|"runtimeSitePackages"' \
    "${VEDICSIGN_ROOT}/backend/app/main.py" 2>/dev/null; then
    add_result blocker PUBLIC_HEALTH_DETAILS "Public health response still exposes internal runtime paths/details"
  else
    add_result pass PUBLIC_HEALTH_DETAILS "Public health response is minimal"
  fi

  if grep -q 'In-memory DAG runner' \
    "${VEDICSIGN_ROOT}/backend/app/services/core_job_runtime.py" 2>/dev/null; then
    add_result blocker CORE_JOB_PERSISTENCE "Core report jobs still depend on in-process memory and cannot survive deployment restarts"
  else
    add_result pass CORE_JOB_PERSISTENCE "No in-memory-only core job runtime was detected"
  fi

  if [[ -f "${VEDICSIGN_ROOT}/backend/alembic.ini" \
    && -d "${VEDICSIGN_ROOT}/backend/alembic" ]]; then
    add_result pass DATABASE_MIGRATIONS "Alembic production migrations are configured"
  else
    add_result blocker DATABASE_MIGRATIONS "backend/alembic.ini and backend/alembic are required for production migrations"
  fi

  vd_has_command git \
    && add_result pass TOOL_GIT "Git is installed" \
    || add_result blocker TOOL_GIT "Git is not installed"
  vd_has_command docker \
    && add_result pass TOOL_DOCKER "Docker is installed" \
    || add_result blocker TOOL_DOCKER "Docker is not installed"
  if vd_has_command docker && docker compose version >/dev/null 2>&1; then
    add_result pass TOOL_COMPOSE "Docker Compose plugin is available"
    if [[ -f "${env_file}" && -f "${VEDICSIGN_ROOT}/compose.production.yml" ]]; then
      if VEDICSIGN_ENV_FILE="${env_file}" \
        VEDICSIGN_IMAGE_TAG=doctor \
        VEDICSIGN_GIT_SHA="$(vd_git_sha)" \
        VEDICSIGN_BUILD_TIME=doctor \
        docker compose --env-file "${env_file}" \
          -f "${VEDICSIGN_ROOT}/compose.production.yml" config --quiet >/dev/null 2>&1; then
        add_result pass COMPOSE_CONFIG "Production Compose configuration is valid"
      else
        add_result blocker COMPOSE_CONFIG "Production Compose configuration is invalid"
      fi
    fi
  else
    add_result blocker TOOL_COMPOSE "Docker Compose plugin is unavailable"
  fi
}

render_text() {
  local index level message
  vd_heading "VedicSign Release Doctor"
  vd_info "Source: $(vd_git_sha)"
  vd_info "Configuration: ${env_file}"
  printf '\n'
  for ((index = 0; index < ${#result_levels[@]}; index++)); do
    level="${result_levels[$index]}"
    message="${result_messages[$index]}"
    case "${level}" in
      pass) vd_ok "${message}" ;;
      warning) vd_warn "${message}" ;;
      blocker) vd_error "${message}" ;;
    esac
  done
  printf '\n%sSummary:%s %s passed · %s warnings · %s blockers\n' \
    "${VEDICSIGN_BOLD}" "${VEDICSIGN_RESET}" "${passed}" "${warnings}" "${blockers}"
}

render_json() {
  local index separator=""
  printf '{"ok":%s,"scope":"%s","sourceSha":"%s","counts":{"passed":%d,"warnings":%d,"blockers":%d},"checks":[' \
    "$([[ ${blockers} -eq 0 ]] && printf true || printf false)" \
    "$(vd_json_escape "${scope}")" "$(vd_json_escape "$(vd_git_sha)")" \
    "${passed}" "${warnings}" "${blockers}"
  for ((index = 0; index < ${#result_levels[@]}; index++)); do
    printf '%s{"level":"%s","code":"%s","message":"%s"}' \
      "${separator}" \
      "$(vd_json_escape "${result_levels[$index]}")" \
      "$(vd_json_escape "${result_codes[$index]}")" \
      "$(vd_json_escape "${result_messages[$index]}")"
    separator=','
  done
  printf ']}\n'
}

check_configuration
[[ "${scope}" == "all" ]] && check_repository

if [[ "${output_json}" == true ]]; then
  render_json
else
  render_text
fi

[[ ${blockers} -eq 0 ]] || exit 2
