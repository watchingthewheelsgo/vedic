#!/usr/bin/env bash

set -Eeuo pipefail

VEDICSIGN_DEPLOY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${VEDICSIGN_DEPLOY_ROOT}/scripts/production/cli.sh" "$@"
