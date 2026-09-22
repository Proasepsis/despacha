#!/bin/bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run this script as root" >&2
    exit 2
fi
if [[ -z "${RUNNER_TOKEN:-}" ]]; then
    echo "Set RUNNER_TOKEN to a one-time GitHub runner registration token" >&2
    exit 2
fi

version=2.337.0
archive="actions-runner-linux-x64-$version.tar.gz"
checksum=70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613
runner_root=/opt/actions-runner
runner_user=github-runner
deploy_group=despacha-deploy

getent group "$deploy_group" >/dev/null || groupadd --system "$deploy_group"
if ! id "$runner_user" >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash "$runner_user"
fi
usermod -aG "docker,$deploy_group" "$runner_user"
install -d -o "$runner_user" -g "$runner_user" -m 750 "$runner_root"
install -d -o "$runner_user" -g "$runner_user" -m 700 \
    /opt/despacha-cicd-backups/staging \
    /opt/despacha-cicd-backups/production
chgrp "$deploy_group" /opt/despacha/.env /opt/despacha-dev/.env
chmod 640 /opt/despacha/.env /opt/despacha-dev/.env

if [[ ! -x "$runner_root/config.sh" ]]; then
    temporary="$(mktemp -d)"
    curl --fail --location --output "$temporary/$archive" \
        "https://github.com/actions/runner/releases/download/v$version/$archive"
    printf '%s  %s\n' "$checksum" "$temporary/$archive" | sha256sum --check --status
    tar -xzf "$temporary/$archive" -C "$runner_root"
    chown -R "$runner_user:$runner_user" "$runner_root"
    rm -rf "$temporary"
fi

if [[ ! -f "$runner_root/.runner" ]]; then
    runuser -u "$runner_user" -- "$runner_root/config.sh" \
        --unattended \
        --url https://github.com/Proasepsis/despacha \
        --token "$RUNNER_TOKEN" \
        --name despacha-35 \
        --labels despacha-deploy \
        --work _work \
        --replace
fi

pushd "$runner_root" >/dev/null
./svc.sh install "$runner_user"
./svc.sh start
popd >/dev/null
echo "GitHub Actions runner installed as $runner_user"
