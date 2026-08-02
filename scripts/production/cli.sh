#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
  cat <<'EOF'
VedicSign production deployment CLI

Usage:
  ./deploy.sh setup [options]       First-time guided configuration
  ./deploy.sh doctor [options]      Read-only release readiness checks
  ./deploy.sh status [--json]       Show source and running-service status
  ./deploy.sh backup [options]      Back up local session artifacts
  ./deploy.sh restore-check         Validate the latest artifact backup
  ./deploy.sh rollback [options]    Restore the previous known-good release
  ./deploy.sh [options]             Deploy the configured release

Common options:
  --env-file <path>                 Configuration file (default: .env.production)
  --dry-run                         Show checks and planned work without changes
  --yes                             Accept safe prompts when configuration is complete
  --json                            Machine-readable output where supported
  --ref <sha|tag|branch>            Deploy a specific Git ref
  --help                            Show this help

Setup guides the first VPS deployment. The default command updates a clean VPS
checkout, builds versioned images, starts the release, runs smoke tests, and
keeps the previous application image as a rollback target.
EOF
}

command_name="deploy"
if [[ $# -gt 0 ]]; then
  case "$1" in
    setup|doctor|status|backup|restore-check|rollback|deploy)
      command_name="$1"
      shift
      ;;
    help|-h|--help)
      usage
      exit 0
      ;;
  esac
fi

case "${command_name}" in
  setup)
    exec "${SCRIPT_DIR}/setup.sh" "$@"
    ;;
  doctor)
    exec "${SCRIPT_DIR}/doctor.sh" "$@"
    ;;
  status)
    exec "${SCRIPT_DIR}/status.sh" "$@"
    ;;
  backup)
    exec "${SCRIPT_DIR}/backup.sh" "$@"
    ;;
  restore-check)
    exec "${SCRIPT_DIR}/restore-check.sh" "$@"
    ;;
  rollback)
    exec "${SCRIPT_DIR}/rollback.sh" "$@"
    ;;
  deploy)
    exec "${SCRIPT_DIR}/release.sh" "$@"
    ;;
esac
