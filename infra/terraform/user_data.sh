#!/bin/bash
set -euo pipefail

dnf update -y
dnf install -y docker git curl

systemctl enable --now docker
usermod -aG docker ec2-user

mkdir -p /usr/local/lib/docker/cli-plugins
machine_arch="$(uname -m)"
case "${machine_arch}" in
  x86_64) compose_arch="x86_64" ;;
  aarch64) compose_arch="aarch64" ;;
  *) echo "Unsupported architecture: ${machine_arch}" >&2; exit 1 ;;
esac

curl --fail --location --retry 3 \
  "https://github.com/docker/compose/releases/download/v2.39.4/docker-compose-linux-${compose_arch}" \
  --output /usr/local/lib/docker/cli-plugins/docker-compose
chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose

install -d -o ec2-user -g ec2-user -m 0750 /opt/verimarka
