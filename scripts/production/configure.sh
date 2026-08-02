#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
assume_yes=false
dry_run=false

usage() {
  cat <<'EOF'
Usage: configure.sh [--env-file <path>] [--yes] [--dry-run]

Creates or updates the production environment file without echoing secrets.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    --yes)
      assume_yes=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      vd_die "Unknown configure option: $1" 64
      ;;
  esac
done

if [[ "${assume_yes}" == false && ! -t 0 ]]; then
  vd_die "Interactive setup requires a TTY; provide configuration first or use --yes" 64
fi

value_for() {
  local key="$1" fallback="${2:-}" process_value existing_value
  process_value="${!key:-}"
  if [[ -n "${process_value}" ]]; then
    printf '%s' "${process_value}"
    return
  fi
  existing_value="$(vd_env_value "${env_file}" "${key}" 2>/dev/null || true)"
  if [[ -n "${existing_value}" ]]; then
    printf '%s' "${existing_value}"
  else
    printf '%s' "${fallback}"
  fi
}

prompt_value() {
  local key="$1" label="$2" fallback="${3:-}" secret="${4:-false}" required="${5:-false}"
  local current answer prompt_suffix
  current="$(value_for "${key}" "${fallback}")"

  if [[ "${assume_yes}" == true ]]; then
    if [[ "${required}" == true ]] && vd_is_placeholder "${current}"; then
      vd_die "${key} is required for non-interactive setup" 65
    fi
    printf -v "${key}" '%s' "${current}"
    return
  fi

  if [[ "${secret}" == true ]]; then
    if [[ -n "${current}" ]]; then
      prompt_suffix=" [configured; Enter keeps current]: "
    else
      prompt_suffix=" [required]: "
    fi
    read -r -s -p "${label}${prompt_suffix}" answer
    printf '\n'
  else
    prompt_suffix=""
    [[ -n "${current}" ]] && prompt_suffix=" [${current}]"
    read -r -p "${label}${prompt_suffix}: " answer
  fi

  [[ -n "${answer}" ]] && current="${answer}"
  if [[ "${required}" == true ]] && vd_is_placeholder "${current}"; then
    vd_die "${key} is required" 65
  fi
  [[ "${current}" != *$'\n'* && "${current}" != *$'\r'* ]] \
    || vd_die "${key} cannot contain a newline" 65
  printf -v "${key}" '%s' "${current}"
}

dotenv_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

vd_heading "VedicSign Production Configuration"
vd_info "Secrets are hidden and the generated file will use mode 0600."

prompt_value SITE_DOMAIN "Canonical Web domain" "vedicsign.ai" false true
vd_is_domain "${SITE_DOMAIN}" || vd_die "Invalid SITE_DOMAIN: ${SITE_DOMAIN}" 65

API_DOMAIN="api.${SITE_DOMAIN}"
ALLOWED_ORIGINS="https://${SITE_DOMAIN}"
VITE_API_BASE_URL="https://${API_DOMAIN}/v1"
CREEM_SUCCESS_URL="https://${SITE_DOMAIN}/account?billing=success"

prompt_value VITE_CLERK_PUBLISHABLE_KEY "Clerk publishable key" "" true true
prompt_value CLERK_SECRET_KEY "Clerk secret key" "" true true
prompt_value VEDIC_ADMIN_USER_IDS "Admin Clerk user IDs (comma-separated, optional)" "" false false
prompt_value VEDIC_ADMIN_EMAILS "Admin emails (comma-separated, optional)" "" false false

prompt_value DATABASE_URL "PostgreSQL connection URL" "" true true
[[ "${DATABASE_URL}" == postgresql://* || "${DATABASE_URL}" == postgres://* ]] \
  || vd_die "DATABASE_URL must use PostgreSQL" 65

prompt_value DEEPSEEK_API_KEY "DeepSeek API key (leave empty when using Anthropic auth)" "" true false
prompt_value ANTHROPIC_AUTH_TOKEN "Anthropic-compatible auth token (optional)" "" true false
prompt_value ANTHROPIC_API_KEY "Anthropic API key (optional)" "" true false
if vd_is_placeholder "${DEEPSEEK_API_KEY}" \
  && vd_is_placeholder "${ANTHROPIC_AUTH_TOKEN}" \
  && vd_is_placeholder "${ANTHROPIC_API_KEY}"; then
  vd_die "Configure at least one agent token: DEEPSEEK_API_KEY, ANTHROPIC_AUTH_TOKEN, or ANTHROPIC_API_KEY" 65
fi
prompt_value ANTHROPIC_BASE_URL "Claude-compatible agent base URL" \
  "https://api.deepseek.com/anthropic" false true
prompt_value ANTHROPIC_MODEL "Agent model" "deepseek-v4-pro[1m]" false true
prompt_value ANTHROPIC_DEFAULT_OPUS_MODEL "Agent opus model mapping" "${ANTHROPIC_MODEL}" false true
prompt_value ANTHROPIC_DEFAULT_SONNET_MODEL "Agent sonnet model mapping" "${ANTHROPIC_MODEL}" false true
prompt_value ANTHROPIC_DEFAULT_HAIKU_MODEL "Agent haiku model mapping" "deepseek-v4-flash" false true
prompt_value AGENT_EFFORT "Agent effort" "max" false true
prompt_value AGENT_MAX_TURNS "Agent maximum turns" "8" false true
prompt_value AGENT_TIMEOUT_MS "Agent timeout in milliseconds" "420000" false true

prompt_value AMAP_WEB_SERVICE_KEY "Amap Web Service key (optional)" "" true false
prompt_value AMAP_PLACE_FALLBACK_ENABLED "Enable Amap fallback (true/false)" "false" false true

prompt_value CREEM_TEST_MODE "Use Creem test mode (true/false)" "true" false true
[[ "${CREEM_TEST_MODE}" == "true" || "${CREEM_TEST_MODE}" == "false" ]] \
  || vd_die "CREEM_TEST_MODE must be true or false" 65
prompt_value CREEM_API_KEY "Creem API key (optional during non-billing staging)" "" true false
prompt_value CREEM_WEBHOOK_SECRET "Creem webhook secret (optional during staging)" "" true false
prompt_value CREEM_PRODUCT_PRO_MONTHLY "Creem monthly product ID (optional during staging)" "" false false
prompt_value CREEM_PRODUCT_PRO_YEARLY "Creem yearly product ID (optional)" "" false false
prompt_value CREEM_PRODUCT_SINGLE_REPORT "Creem single-report product ID (optional)" "" false false

SESSION_DATA_DIR="$(value_for SESSION_DATA_DIR /var/lib/vedicsign/sessions)"
BACKUP_DIR="$(value_for BACKUP_DIR /var/backups/vedicsign)"
VEDICSIGN_UID="$(value_for VEDICSIGN_UID "$(id -u)")"
VEDICSIGN_GID="$(value_for VEDICSIGN_GID "$(id -g)")"

vd_heading "Configuration Summary"
vd_ok "Web: https://${SITE_DOMAIN}"
vd_ok "API: https://${API_DOMAIN}"
vd_ok "PostgreSQL: configured (secret hidden)"
vd_ok "Clerk: configured (secrets hidden)"
vd_ok "Agent runtime: ${ANTHROPIC_BASE_URL} · ${ANTHROPIC_MODEL}"
if [[ "${CREEM_TEST_MODE}" == "true" ]]; then
  vd_warn "Creem: test mode"
else
  vd_ok "Creem: live mode"
fi

if [[ "${dry_run}" == true ]]; then
  vd_info "Dry run: no configuration was written."
  exit 0
fi

env_dir="$(cd "$(dirname "${env_file}")" && pwd)"
umask 077
temp_file="$(mktemp "${env_dir}/.env.production.tmp.XXXXXX")"
trap 'rm -f "${temp_file}"' EXIT

{
  printf '%s\n' '# Generated by ./deploy.sh setup. Do not commit this file.'
  printf 'APP_ENV=production\n'
  printf 'SITE_DOMAIN=%s\n' "$(dotenv_quote "${SITE_DOMAIN}")"
  printf 'API_DOMAIN=%s\n' "$(dotenv_quote "${API_DOMAIN}")"
  printf 'ALLOWED_ORIGINS=%s\n' "$(dotenv_quote "${ALLOWED_ORIGINS}")"
  printf 'VITE_API_BASE_URL=%s\n' "$(dotenv_quote "${VITE_API_BASE_URL}")"
  printf '\n'
  printf 'VITE_CLERK_PUBLISHABLE_KEY=%s\n' "$(dotenv_quote "${VITE_CLERK_PUBLISHABLE_KEY}")"
  printf 'CLERK_SECRET_KEY=%s\n' "$(dotenv_quote "${CLERK_SECRET_KEY}")"
  printf 'VEDIC_AUTH_MODE=clerk\n'
  printf 'VEDIC_ADMIN_USER_IDS=%s\n' "$(dotenv_quote "${VEDIC_ADMIN_USER_IDS}")"
  printf 'VEDIC_ADMIN_EMAILS=%s\n' "$(dotenv_quote "${VEDIC_ADMIN_EMAILS}")"
  printf '\n'
  printf 'DATABASE_URL=%s\n' "$(dotenv_quote "${DATABASE_URL}")"
  printf 'DATABASE_ECHO=false\n'
  printf '\n'
  printf 'DEEPSEEK_API_KEY=%s\n' "$(dotenv_quote "${DEEPSEEK_API_KEY}")"
  printf 'VEDIC_AI_MODE=\n'
  printf 'ANTHROPIC_AUTH_TOKEN=%s\n' "$(dotenv_quote "${ANTHROPIC_AUTH_TOKEN}")"
  printf 'ANTHROPIC_API_KEY=%s\n' "$(dotenv_quote "${ANTHROPIC_API_KEY}")"
  printf 'ANTHROPIC_BASE_URL=%s\n' "$(dotenv_quote "${ANTHROPIC_BASE_URL}")"
  printf 'ANTHROPIC_MODEL=%s\n' "$(dotenv_quote "${ANTHROPIC_MODEL}")"
  printf 'ANTHROPIC_DEFAULT_OPUS_MODEL=%s\n' "$(dotenv_quote "${ANTHROPIC_DEFAULT_OPUS_MODEL}")"
  printf 'ANTHROPIC_DEFAULT_SONNET_MODEL=%s\n' "$(dotenv_quote "${ANTHROPIC_DEFAULT_SONNET_MODEL}")"
  printf 'ANTHROPIC_DEFAULT_HAIKU_MODEL=%s\n' "$(dotenv_quote "${ANTHROPIC_DEFAULT_HAIKU_MODEL}")"
  printf 'AGENT_EFFORT=%s\n' "$(dotenv_quote "${AGENT_EFFORT}")"
  printf 'AGENT_MAX_TURNS=%s\n' "$(dotenv_quote "${AGENT_MAX_TURNS}")"
  printf 'AGENT_TIMEOUT_MS=%s\n' "$(dotenv_quote "${AGENT_TIMEOUT_MS}")"
  printf '\n'
  printf 'AMAP_WEB_SERVICE_KEY=%s\n' "$(dotenv_quote "${AMAP_WEB_SERVICE_KEY}")"
  printf 'AMAP_PLACE_FALLBACK_ENABLED=%s\n' "${AMAP_PLACE_FALLBACK_ENABLED}"
  printf '\n'
  printf 'CREEM_API_KEY=%s\n' "$(dotenv_quote "${CREEM_API_KEY}")"
  printf 'CREEM_WEBHOOK_SECRET=%s\n' "$(dotenv_quote "${CREEM_WEBHOOK_SECRET}")"
  printf 'CREEM_TEST_MODE=%s\n' "${CREEM_TEST_MODE}"
  printf 'CREEM_SUCCESS_URL=%s\n' "$(dotenv_quote "${CREEM_SUCCESS_URL}")"
  printf 'CREEM_PRODUCT_PRO_MONTHLY=%s\n' "$(dotenv_quote "${CREEM_PRODUCT_PRO_MONTHLY}")"
  printf 'CREEM_PRODUCT_PRO_YEARLY=%s\n' "$(dotenv_quote "${CREEM_PRODUCT_PRO_YEARLY}")"
  printf 'CREEM_PRODUCT_SINGLE_REPORT=%s\n' "$(dotenv_quote "${CREEM_PRODUCT_SINGLE_REPORT}")"
  printf '\n'
  printf 'HOST=0.0.0.0\n'
  printf 'PORT=8787\n'
  printf 'RELOAD=false\n'
  printf 'VEDICSIGN_UID=%s\n' "${VEDICSIGN_UID}"
  printf 'VEDICSIGN_GID=%s\n' "${VEDICSIGN_GID}"
  printf 'SESSION_DATA_DIR=%s\n' "$(dotenv_quote "${SESSION_DATA_DIR}")"
  printf 'BACKUP_DIR=%s\n' "$(dotenv_quote "${BACKUP_DIR}")"
} > "${temp_file}"

chmod 600 "${temp_file}"
mv "${temp_file}" "${env_file}"
trap - EXIT
vd_ok "Wrote ${env_file} with mode 0600"
