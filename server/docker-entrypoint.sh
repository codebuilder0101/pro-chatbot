#!/bin/sh
set -e

case "${1:-agent}" in
  agent)
    exec python -m agent.agent start
    ;;
  dev)
    exec python -m agent.agent dev
    ;;
  token-server)
    exec uvicorn token_server.main:app \
      --host 0.0.0.0 --port "${TOKEN_SERVER_PORT:-8080}"
    ;;
  *)
    exec "$@"
    ;;
esac
