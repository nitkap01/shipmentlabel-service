#!/bin/bash
# SHIP-6: run the backend test suite on the server against a SEPARATE database (shipmentlabel_test), never the live one.
#   cd /opt/shipmentlabel/app && bash deploy/aws/run-tests.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select 1 from pg_database where datname='shipmentlabel_test'" | grep -q 1 \
  || docker compose exec -T postgres createdb -U "$POSTGRES_USER" shipmentlabel_test
docker run --rm --network app_default -v "$PWD/backend:/src:ro" -v "$PWD/migrations:/migrations:ro" \
  -e DATABASE_URL="postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/shipmentlabel_test" \
  -e MIGRATIONS_DIR=/migrations \
  python:3.12-slim sh -c 'cp -r /src /work && cd /work && pip install -q --root-user-action=ignore -e ".[dev]" && python -m pytest -q -p no:cacheprovider'
