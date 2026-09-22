#!/bin/bash
set -euo pipefail

environment="${1:-}"
requested_image="${2:-}"
compose_file="${3:-}"

case "$environment" in
    staging)
        target=/opt/despacha-dev
        project=despacha-dev
        port=8001
        container=despacha-dev-web-1
        db_container=despacha-dev-db-1
        ;;
    production)
        target=/opt/despacha
        project=despacha
        port=8000
        container=despacha-web-1
        db_container=despacha-db-1
        ;;
    *)
        echo "Environment must be staging or production" >&2
        exit 2
        ;;
esac

if [[ ! "$requested_image" =~ ^ghcr\.io/proasepsis/despacha(:sha-[0-9a-f]{40}|@sha256:[0-9a-f]{64})$ ]]; then
    echo "Image reference is not an approved Despacha image" >&2
    exit 2
fi
if [[ ! -f "$compose_file" || ! -r "$target/.env" ]]; then
    echo "Compose file or environment file is unavailable" >&2
    exit 2
fi

docker pull "$requested_image"
resolved_image="$(
    docker image inspect "$requested_image" --format '{{range .RepoDigests}}{{println .}}{{end}}' |
        awk '/^ghcr\.io\/proasepsis\/despacha@sha256:/ { print; exit }'
)"
if [[ ! "$resolved_image" =~ ^ghcr\.io/proasepsis/despacha@sha256:[0-9a-f]{64}$ ]]; then
    echo "Could not resolve the immutable image digest" >&2
    exit 1
fi

candidate_id="$(docker image inspect "$resolved_image" --format '{{.Id}}')"
if [[ "$environment" == production ]]; then
    staging_id="$(docker inspect despacha-dev-web-1 --format '{{.Image}}')"
    if [[ "$candidate_id" != "$staging_id" ]]; then
        echo "Production promotion rejected: image is not running in staging" >&2
        exit 1
    fi
fi

backup_dir="/opt/despacha-cicd-backups/$environment"
mkdir -p "$backup_dir"
backup="$backup_dir/$(date -u +%Y%m%dT%H%M%SZ).dump"
docker exec "$db_container" sh -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup"
chmod 600 "$backup"
if [[ ! -s "$backup" ]]; then
    echo "Database backup is empty" >&2
    exit 1
fi
find "$backup_dir" -type f -name '*.dump' -mtime +14 -delete

previous_image="$(docker inspect "$container" --format '{{.Config.Image}}')"
export WEB_IMAGE="$resolved_image"
export ENV_FILE="$target/.env"

compose=(
    docker compose
    --project-name "$project"
    --project-directory "$target"
    --env-file "$target/.env"
    -f "$compose_file"
)
"${compose[@]}" up -d --no-deps --force-recreate web

healthy=false
for _ in $(seq 1 30); do
    status="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/" || true)"
    if [[ "$status" == 200 || "$status" == 302 ]]; then
        healthy=true
        break
    fi
    sleep 2
done

if [[ "$healthy" != true ]]; then
    docker logs --tail 100 "$container" >&2 || true
    echo "Health check failed; restoring previous application image" >&2
    export WEB_IMAGE="$previous_image"
    "${compose[@]}" up -d --no-deps --force-recreate web
    exit 1
fi

printf '%s\n' "$resolved_image" > "$backup_dir/current-image"
echo "Deployed $resolved_image to $environment; backup: $backup"
