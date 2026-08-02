#!/usr/bin/env bash

set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${TEST_DIR}/../../.." && pwd)"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vedicsign-deploy-test.XXXXXX")"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

passed=0

pass() {
  passed=$((passed + 1))
  printf 'ok %d - %s\n' "${passed}" "$1"
}

fail() {
  printf 'not ok %d - %s\n' "$((passed + 1))" "$1" >&2
  exit 1
}

assert_contains() {
  local value="$1" expected="$2" label="$3"
  [[ "${value}" == *"${expected}"* ]] || fail "${label}: missing ${expected}"
  pass "${label}"
}

printf '1..18\n'

help_output="$("${ROOT}/deploy.sh" --help)"
assert_contains "${help_output}" './deploy.sh setup' 'help lists setup command'

status_output="$("${ROOT}/deploy.sh" status --json)"
assert_contains "${status_output}" '"sourceSha"' 'status has machine-readable source SHA'

dry_run_env="${TEMP_ROOT}/dry-run.env"
dry_run_output="$(
  SITE_DOMAIN=vedicsign.ai \
  VITE_CLERK_PUBLISHABLE_KEY=pk_test_fixture \
  CLERK_SECRET_KEY=sk_test_fixture_do_not_print \
  DATABASE_URL='postgresql://fixture:password@db.example.com:5432/vedicsign?sslmode=require' \
  DEEPSEEK_API_KEY=agent_fixture_do_not_print \
  ANTHROPIC_MODEL='deepseek-v4-pro[1m]' \
  CREEM_TEST_MODE=true \
  SESSION_DATA_DIR="${TEMP_ROOT}/dry-sessions" \
  BACKUP_DIR="${TEMP_ROOT}/dry-backups" \
    "${ROOT}/deploy.sh" setup --yes --dry-run --env-file "${dry_run_env}" 2>&1
)"
[[ ! -e "${dry_run_env}" ]] || fail 'setup dry run does not write configuration'
pass 'setup dry run does not write configuration'
assert_contains "${dry_run_output}" 'Dry run' 'setup dry run reports its non-mutating mode'

generated_env="${TEMP_ROOT}/generated.env"
SITE_DOMAIN=vedicsign.ai \
VITE_CLERK_PUBLISHABLE_KEY=pk_test_fixture \
CLERK_SECRET_KEY=sk_test_fixture_do_not_print \
DATABASE_URL='postgresql://fixture:password@db.example.com:5432/vedicsign?sslmode=require' \
DEEPSEEK_API_KEY=agent_fixture_do_not_print \
ANTHROPIC_MODEL='deepseek-v4-pro[1m]' \
CREEM_TEST_MODE=true \
SESSION_DATA_DIR="${TEMP_ROOT}/sessions" \
BACKUP_DIR="${TEMP_ROOT}/backups" \
  "${ROOT}/scripts/production/configure.sh" --yes --env-file "${generated_env}" \
  > "${TEMP_ROOT}/configure.out" 2>&1

[[ -f "${generated_env}" ]] || fail 'non-interactive configure writes an environment file'
pass 'non-interactive configure writes an environment file'

mode="$(stat -c '%a' "${generated_env}" 2>/dev/null || stat -f '%Lp' "${generated_env}")"
[[ "${mode}" == '600' ]] || fail 'generated environment file uses mode 0600'
pass 'generated environment file uses mode 0600'

configure_output="$(<"${TEMP_ROOT}/configure.out")"
[[ "${configure_output}" != *'sk_test_fixture_do_not_print'* ]] \
  || fail 'configure output does not reveal secrets'
[[ "${configure_output}" != *'agent_fixture_do_not_print'* ]] \
  || fail 'configure output does not reveal agent token'
pass 'configure output does not reveal secrets'

doctor_output="$("${ROOT}/deploy.sh" doctor --scope config --env-file "${generated_env}" --json)"
assert_contains "${doctor_output}" '"ok":true' 'doctor accepts a valid generated configuration'

mkdir -p "${TEMP_ROOT}/sessions/session_fixture"
printf 'fixture\n' > "${TEMP_ROOT}/sessions/session_fixture/report.md"
backup_output="$("${ROOT}/deploy.sh" backup --env-file "${generated_env}" --json)"
assert_contains "${backup_output}" '"ok":true' 'backup creates an artifact archive'
archive_count="$(find "${TEMP_ROOT}/backups" -type f -name 'sessions-*.tar.gz' | wc -l | tr -d ' ')"
[[ "${archive_count}" == '1' ]] || fail 'backup writes exactly one archive'
pass 'backup writes exactly one archive'
restore_output="$("${ROOT}/deploy.sh" restore-check --env-file "${generated_env}" --json)"
assert_contains "${restore_output}" '"files":1' 'restore-check validates the isolated backup contents'

set +e
repository_doctor_output="$("${ROOT}/deploy.sh" doctor --scope all --env-file "${generated_env}" --json 2>&1)"
set -e
assert_contains "${repository_doctor_output}" '"code":"COMPOSE_CONFIG"' 'doctor validates the production Compose file'

set +e
release_dry_run_output="$("${ROOT}/deploy.sh" --dry-run --yes --no-pull --env-file "${generated_env}" 2>&1)"
release_dry_run_status=$?
set -e
[[ ${release_dry_run_status} -eq 2 ]] || fail 'release dry run returns the doctor blocker status'
pass 'release dry run returns the doctor blocker status'
[[ ! -e "${ROOT}/.deploy" ]] || fail 'release dry run does not create deployment state'
pass 'release dry run does not create deployment state'

invalid_env="${TEMP_ROOT}/invalid.env"
cp "${generated_env}" "${invalid_env}"
awk '
  /^API_DOMAIN=/ { print "API_DOMAIN=wrong.example.com"; next }
  { print }
' "${generated_env}" > "${invalid_env}.tmp"
mv "${invalid_env}.tmp" "${invalid_env}"
chmod 600 "${invalid_env}"

set +e
invalid_output="$("${ROOT}/deploy.sh" doctor --scope config --env-file "${invalid_env}" --json 2>&1)"
invalid_status=$?
set -e
[[ ${invalid_status} -eq 2 ]] || fail 'doctor rejects invalid configuration with exit code 2'
pass 'doctor rejects invalid configuration with exit code 2'
assert_contains "${invalid_output}" '"code":"API_DOMAIN"' 'doctor identifies the invalid API domain'

set +e
rollback_output="$("${ROOT}/deploy.sh" rollback --json 2>&1)"
rollback_status=$?
set -e
[[ ${rollback_status} -eq 69 ]] || fail 'unavailable rollback fails safely'
pass 'unavailable rollback fails safely'
assert_contains "${rollback_output}" 'ROLLBACK_NOT_AVAILABLE' 'unavailable rollback reports a stable error code'
