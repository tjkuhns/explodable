#!/bin/bash
# Wait for Docker containers (PostgreSQL + Redis) to be healthy before starting Celery.
# Exits 0 when both are healthy, exits 1 after timeout.
# Also checks basic Redis/Postgres connectivity as fallback if Docker CLI unavailable.

TIMEOUT=120
ELAPSED=0
DOCKER=/usr/bin/docker

while [ $ELAPSED -lt $TIMEOUT ]; do
    if [ -x "$DOCKER" ] && "$DOCKER" info >/dev/null 2>&1; then
        PG_HEALTHY=$("$DOCKER" inspect --format='{{.State.Health.Status}}' explodable_postgres 2>/dev/null)
        REDIS_HEALTHY=$("$DOCKER" inspect --format='{{.State.Health.Status}}' explodable_redis 2>/dev/null)

        if [ "$PG_HEALTHY" = "healthy" ] && [ "$REDIS_HEALTHY" = "healthy" ]; then
            echo "Docker containers healthy (postgres=$PG_HEALTHY, redis=$REDIS_HEALTHY)"
            exit 0
        fi
    else
        # Fallback: check ports directly if Docker CLI not accessible
        if (echo > /dev/tcp/localhost/5432) 2>/dev/null && (echo > /dev/tcp/localhost/6379) 2>/dev/null; then
            echo "Ports 5432 and 6379 accepting connections (Docker CLI not accessible)"
            exit 0
        fi
    fi

    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

echo "Timeout waiting for Docker containers (postgres=${PG_HEALTHY:-unknown}, redis=${REDIS_HEALTHY:-unknown})"
exit 1
