#!/usr/bin/env bash
set -euo pipefail

echo "Pruefe DNS/HTTPS aus einem Node-Container ..."
docker run --rm node:22-alpine sh -lc '
  echo "Node: $(node --version)"
  echo "npm:  $(npm --version)"
  npm config set fetch-timeout 10000
  npm config set fetch-retries 1
  npm ping --registry=https://registry.npmjs.org/
'

echo "OK: npm registry ist aus Docker erreichbar."
