#!/bin/sh
set -eu
exec python -m uvicorn hadis_web.app:create_app --factory --host 0.0.0.0 --port 8080 \
  --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips "${HADIS_PROXY_IP:?Proxy IP required}" \
  --limit-concurrency 64 --backlog 128 --timeout-keep-alive 5 --no-server-header --no-access-log
