#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/root/complex-services-web/blastex}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://blastex.complex-services.ru/health}"
HEALTH_RETRIES="${HEALTH_RETRIES:-40}"
HEALTH_INTERVAL_SECONDS="${HEALTH_INTERVAL_SECONDS:-3}"

cd "$APP_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: $APP_DIR/.env is missing" >&2
  exit 1
fi

docker compose -f "$COMPOSE_FILE" config -q

for image in blastex-api blastex-web; do
  if docker image inspect "${image}:latest" >/dev/null 2>&1; then
    docker tag "${image}:latest" "${image}:rollback"
  fi
done

rollback() {
  trap - ERR
  echo "ERROR: deployment failed; restoring previous images" >&2
  for image in blastex-api blastex-web; do
    if docker image inspect "${image}:rollback" >/dev/null 2>&1; then
      docker tag "${image}:rollback" "${image}:latest"
    fi
  done
  docker compose -f "$COMPOSE_FILE" up -d --no-build --force-recreate || true
}
trap rollback ERR

docker compose -f "$COMPOSE_FILE" build
docker compose -f "$COMPOSE_FILE" up -d

for attempt in $(seq 1 "$HEALTH_RETRIES"); do
  api_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' blastex-api 2>/dev/null || true)"
  if [[ "$api_health" == "healthy" ]]; then
    break
  fi
  if [[ "$attempt" -eq "$HEALTH_RETRIES" ]]; then
    echo "ERROR: API did not become healthy" >&2
    docker logs blastex-api --tail 100 >&2 || true
    false
  fi
  sleep "$HEALTH_INTERVAL_SECONDS"
done

docker exec blastex-web wget -qO- http://127.0.0.1/health >/dev/null
curl -fsS --retry 5 --retry-delay 3 --max-time 20 "$PUBLIC_HEALTH_URL" >/dev/null

trap - ERR
docker compose -f "$COMPOSE_FILE" ps
echo "BlastEX deployment completed successfully"
