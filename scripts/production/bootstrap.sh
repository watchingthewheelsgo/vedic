#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

output_json=false
ensure_runtime=false
assume_yes=false
dry_run=false
prepare_paths=false
env_file="${VEDICSIGN_DEFAULT_ENV_FILE}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) output_json=true; shift ;;
    --ensure) ensure_runtime=true; shift ;;
    --yes) assume_yes=true; shift ;;
    --dry-run) dry_run=true; shift ;;
    --prepare-paths) prepare_paths=true; shift ;;
    --env-file)
      [[ $# -ge 2 ]] || vd_die "--env-file requires a path" 64
      env_file="$2"
      shift 2
      ;;
    *) vd_die "Unknown bootstrap option: $1" 64 ;;
  esac
done

os_name="$(uname -s)"
architecture="$(uname -m)"
docker_version="missing"
compose_version="missing"
git_version="missing"

vd_has_command docker && docker_version="$(docker --version 2>/dev/null | head -n 1)"
vd_has_command docker && docker compose version >/dev/null 2>&1 \
  && compose_version="$(docker compose version --short 2>/dev/null || docker compose version 2>/dev/null)"
vd_has_command git && git_version="$(git --version 2>/dev/null)"

if [[ "${output_json}" == true ]]; then
  printf '{"os":"%s","architecture":"%s","git":"%s","docker":"%s","compose":"%s","productionHost":%s}\n' \
    "$(vd_json_escape "${os_name}")" "$(vd_json_escape "${architecture}")" \
    "$(vd_json_escape "${git_version}")" "$(vd_json_escape "${docker_version}")" \
    "$(vd_json_escape "${compose_version}")" \
    "$([[ "${os_name}" == Linux ]] && printf true || printf false)"
  exit 0
fi

vd_heading "Environment Detected"
vd_info "OS: ${os_name} · architecture: ${architecture}"
vd_info "Git: ${git_version}"
vd_info "Docker: ${docker_version}"
vd_info "Compose: ${compose_version}"

if [[ "${os_name}" != "Linux" ]]; then
  vd_warn "This is a development host. The first production target is Ubuntu LTS x86_64."
fi
if [[ "${architecture}" != "x86_64" && "${architecture}" != "amd64" ]]; then
  vd_warn "The first production image has not yet been validated on ${architecture}."
fi

if [[ "${ensure_runtime}" == true ]] && ! vd_has_command docker; then
  if [[ "${dry_run}" == true ]]; then
    vd_warn "Dry run: Docker Engine and Compose would be installed from Docker's official apt repository."
  else
    [[ "${os_name}" == "Linux" ]] || vd_die "Install Docker Desktop manually on this development host" 69
    if [[ "${assume_yes}" == false ]]; then
      read -r -p "Docker is missing. Install Docker Engine and Compose now? (Y/n): " answer
      [[ -z "${answer}" || "${answer}" == [Yy]* ]] || vd_die "Docker installation cancelled" 75
    fi
    "${SCRIPT_DIR}/install-docker.sh"
  fi
fi

if [[ "${ensure_runtime}" == true && "${dry_run}" == false ]]; then
  vd_has_command git || vd_die "Git is required" 69
  vd_has_command curl || vd_die "curl is required" 69
  vd_has_command docker || vd_die "Docker is required" 69
  docker compose version >/dev/null 2>&1 || vd_die "Docker Compose plugin is required" 69

  if ! docker info >/dev/null 2>&1; then
    if [[ "${os_name}" == "Linux" && "$(id -u)" -ne 0 ]] \
      && vd_has_command sudo && sudo docker info >/dev/null 2>&1; then
      vd_die "Docker is installed, but this shell has not picked up docker-group membership. Log out and in, then rerun ./deploy.sh setup" 75
    fi
    vd_die "Docker daemon is not running or is not accessible" 69
  fi
  vd_ok "Docker daemon is reachable"
fi

if [[ "${prepare_paths}" == true ]]; then
  [[ -f "${env_file}" ]] || vd_die "Cannot prepare paths before ${env_file} exists" 65
  session_data_dir="$(vd_env_value "${env_file}" SESSION_DATA_DIR 2>/dev/null || true)"
  backup_dir="$(vd_env_value "${env_file}" BACKUP_DIR 2>/dev/null || true)"
  runtime_uid="$(vd_env_value "${env_file}" VEDICSIGN_UID 2>/dev/null || true)"
  runtime_gid="$(vd_env_value "${env_file}" VEDICSIGN_GID 2>/dev/null || true)"
  [[ "${session_data_dir}" == /* && "${backup_dir}" == /* ]] \
    || vd_die "SESSION_DATA_DIR and BACKUP_DIR must be absolute" 65
  [[ "${runtime_uid}" =~ ^[0-9]+$ && "${runtime_gid}" =~ ^[0-9]+$ ]] \
    || vd_die "VEDICSIGN_UID and VEDICSIGN_GID must be numeric" 65

  if [[ "${dry_run}" == true ]]; then
    vd_info "Dry run: would prepare ${session_data_dir} and ${backup_dir} for ${runtime_uid}:${runtime_gid}"
  else
    sudo_cmd=()
    [[ "$(id -u)" -eq 0 ]] || sudo_cmd=(sudo)
    "${sudo_cmd[@]}" install -d -m 0750 -o "${runtime_uid}" -g "${runtime_gid}" \
      "${session_data_dir}" "${backup_dir}"
    vd_ok "Persistent paths are ready"
  fi
fi

vd_info "SSH and firewall rules were not modified. Public inbound access should be limited to 80/443 and restricted SSH."
