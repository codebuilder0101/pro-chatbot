#!/usr/bin/env bash
# Empacota o backend para subir no VPS.
#
#     bash server/deploy/bundle.sh          # gera iara-server.tar.gz na raiz
#
# O que fica de fora, e por que:
#   .venv/        584 MB de dependencias de Windows, inuteis no Linux
#   .env          segredos nao viajam em tarball; crie o .env no VPS
#   .env.local    aponta para ws://10.0.2.2:7880 e chaves "dev" - se for junto,
#                 vence o .env de producao e o agente tenta falar com o
#                 emulador Android que nao existe la
#   __pycache__/  bytecode compilado para outro sistema
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/iara-server.tar.gz}"

cd "$ROOT"

tar -czf "$OUT" \
    --exclude='server/.venv' \
    --exclude='server/venv' \
    --exclude='server/.env' \
    --exclude='server/.env.local' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='server/metrics' \
    --exclude='*.imx' \
    server/

echo "gerado: $OUT"
echo
echo "tamanho: $(du -h "$OUT" | cut -f1)"
echo
echo "confira que nenhum segredo entrou:"
echo "  tar -tzf $OUT | grep -E '\\.env$|\\.env\\.local$' && echo 'ATENCAO: segredo no pacote' || echo '  ok, sem .env'"
