#!/usr/bin/env bash
# SuperKart - build and start the backend and frontend containers, wait until both are healthy, make their ports
# public (GitHub Codespace), and print the public addresses.
# Run from the repository root:  bash deploy.sh
# Safe to re-run: containers from an earlier run are replaced, so the same command deploys updated files after `git pull`.
set -euo pipefail                                  # stop at the first failing command
cd "$(dirname "$0")"                               # the repository root, wherever the script is started from

NETWORK="superkart-net"
BACKEND_PORT=7860
FRONTEND_PORT=8501

echo "==> 1/5 Docker network '$NETWORK'"
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK"

echo "==> 2/5 Backend: build the image and start the container"
docker build -t superkart-backend backend
docker rm -f backend >/dev/null 2>&1 || true       # remove the container of an earlier run, if any
docker run -d --restart unless-stopped --name backend --network "$NETWORK" \
    -p "$BACKEND_PORT:7860" superkart-backend

echo "==> 3/5 Frontend: build the image and start the container"
docker build -t superkart-frontend frontend
docker rm -f frontend >/dev/null 2>&1 || true
docker run -d --restart unless-stopped --name frontend --network "$NETWORK" \
    -p "$FRONTEND_PORT:8501" superkart-frontend

echo "==> 4/5 Waiting for the health checks (up to 2 minutes)"
for container in backend frontend; do
    status="starting"
    for _ in $(seq 1 24); do                       # 24 x 5 s = 2 minutes
        status="$(docker inspect --format '{{.State.Health.Status}}' "$container")"
        [ "$status" = "healthy" ] && break
        sleep 5
    done
    echo "    $container: $status"
    if [ "$status" != "healthy" ]; then
        echo "    $container did not become healthy - its last log lines:"
        docker logs --tail 30 "$container"
        exit 1
    fi
done
docker ps --filter "name=backend" --filter "name=frontend"

echo "==> 5/5 Public ports"
if [ -n "${CODESPACE_NAME:-}" ]; then
    public="no"
    for _ in $(seq 1 6); do                        # the Codespace detects new ports within a few seconds
        if gh codespace ports visibility "$BACKEND_PORT:public" "$FRONTEND_PORT:public" -c "$CODESPACE_NAME" >/dev/null 2>&1; then
            public="yes"
            break
        fi
        sleep 5
    done
    if [ "$public" = "yes" ]; then
        echo "    Ports $BACKEND_PORT and $FRONTEND_PORT are now Public."
    else
        echo "    Could not change the port visibility automatically:"
        echo "    open the PORTS tab and set ports $BACKEND_PORT and $FRONTEND_PORT to Public (right-click > Port Visibility)."
    fi
    domain="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
    echo
    echo "API (BACKEND_PUBLIC_URL in the notebook): https://$CODESPACE_NAME-$BACKEND_PORT.$domain"
    echo "Web app                                 : https://$CODESPACE_NAME-$FRONTEND_PORT.$domain"
else
    echo "    Not running in a GitHub Codespace - the services are available locally:"
    echo "    API     : http://localhost:$BACKEND_PORT"
    echo "    Web app : http://localhost:$FRONTEND_PORT"
fi
