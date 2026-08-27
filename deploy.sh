#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# deploy.sh — Build & push versioned Docker images for shipmentlabel-service
# Two images (backend + web), built and pushed at the same version tag (D21).
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

API_REPO="nitkap01/shipmentlabel-service-api"
WEB_REPO="nitkap01/shipmentlabel-service-web"
VERSION_FILE="web/src/version.ts"

read -rp "Enter version tag (e.g. v0.2 or 0.2.0): " VERSION
if [[ -z "$VERSION" ]]; then
  echo "Version cannot be empty."
  exit 1
fi
SEMVER="${VERSION#v}"

echo "export const APP_VERSION = '${SEMVER}'" > "$VERSION_FILE"
echo "Updated ${VERSION_FILE} -> ${SEMVER}"

echo ""
echo "Building ${API_REPO}:${VERSION} ..."
docker buildx build --platform linux/amd64 --provenance=false \
  -f backend/Dockerfile -t "${API_REPO}:${VERSION}" --push .

echo ""
echo "Building ${WEB_REPO}:${VERSION} ..."
docker buildx build --platform linux/amd64 --provenance=false \
  -f web/Dockerfile -t "${WEB_REPO}:${VERSION}" --push .

echo ""
echo "Pushed ${API_REPO}:${VERSION} and ${WEB_REPO}:${VERSION}"

read -rp "Commit version bump to git? [y/N] " COMMIT
if [[ "$(echo "${COMMIT}" | tr '[:upper:]' '[:lower:]')" == "y" ]]; then
  git add "$VERSION_FILE"
  git commit -m "chore(release): bump version to ${VERSION}"
  git push
  echo "Committed and pushed version bump"
fi
