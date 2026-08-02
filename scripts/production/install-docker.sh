#!/usr/bin/env bash

set -Eeuo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  printf '[fatal] Automatic Docker installation is only supported on Linux.\n' >&2
  exit 69
fi

if [[ ! -r /etc/os-release ]]; then
  printf '[fatal] Cannot identify this Linux distribution.\n' >&2
  exit 69
fi

# shellcheck disable=SC1091
source /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *)
    printf '[fatal] Automatic Docker installation supports Ubuntu and Debian only (found %s).\n' "${ID:-unknown}" >&2
    exit 69
    ;;
esac

if [[ -z "${VERSION_CODENAME:-}" ]]; then
  printf '[fatal] VERSION_CODENAME is missing from /etc/os-release.\n' >&2
  exit 69
fi

sudo_cmd=()
if [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || {
    printf '[fatal] sudo is required to install Docker.\n' >&2
    exit 77
  }
  sudo_cmd=(sudo)
fi

printf '[info] Installing Docker Engine from the official Docker apt repository...\n'
"${sudo_cmd[@]}" apt-get update
"${sudo_cmd[@]}" apt-get install -y ca-certificates curl gnupg
"${sudo_cmd[@]}" install -m 0755 -d /etc/apt/keyrings

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/vedicsign-docker-install.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o "${temp_root}/docker.asc"
"${sudo_cmd[@]}" gpg --dearmor --batch --yes \
  --output /etc/apt/keyrings/docker.gpg "${temp_root}/docker.asc"
"${sudo_cmd[@]}" chmod a+r /etc/apt/keyrings/docker.gpg

architecture="$(dpkg --print-architecture)"
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/%s %s stable\n' \
  "${architecture}" "${ID}" "${VERSION_CODENAME}" > "${temp_root}/docker.list"
"${sudo_cmd[@]}" install -m 0644 "${temp_root}/docker.list" /etc/apt/sources.list.d/docker.list

"${sudo_cmd[@]}" apt-get update
"${sudo_cmd[@]}" apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

if command -v systemctl >/dev/null 2>&1; then
  "${sudo_cmd[@]}" systemctl enable --now docker
fi

if [[ "$(id -u)" -ne 0 ]]; then
  "${sudo_cmd[@]}" usermod -aG docker "$(id -un)"
fi

printf '[ok] Docker Engine and Compose plugin are installed.\n'
