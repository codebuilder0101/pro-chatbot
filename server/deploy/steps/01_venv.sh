#!/usr/bin/env bash
# Cria o ambiente Python do projeto no VPS e instala as dependencias.
#
# Nada aqui e' global: tudo vive em /var/www/pro-chatbot/.venv. O unico pacote
# de sistema instalado e' o ffmpeg, exigido pelos plugins de audio, e ele nao
# conflita com nada do que ja roda na maquina.
set -euo pipefail

APP=/var/www/pro-chatbot
cd "$APP"

echo "=== ffmpeg (unico pacote de sistema) ==="
if command -v ffmpeg >/dev/null; then
    echo "ja instalado"
else
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends ffmpeg
    echo "instalado: $(ffmpeg -version | head -1)"
fi

echo
echo "=== venv ==="
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
./.venv/bin/python -m pip install --quiet --upgrade pip
echo "python: $(./.venv/bin/python --version)"

echo
echo "=== dependencias (leva alguns minutos) ==="
./.venv/bin/python -m pip install --quiet -r requirements.txt 2>&1 | tail -5

echo
echo "=== conferindo o que importa ==="
./.venv/bin/python - <<'PY'
import importlib

for mod, rotulo in [
    ("livekit.agents", "livekit-agents"),
    ("livekit.plugins.deepgram", "plugin deepgram"),
    ("livekit.plugins.elevenlabs", "plugin elevenlabs"),
    ("livekit.plugins.silero", "plugin silero"),
    ("livekit.plugins.bithuman", "plugin bithuman"),
    ("bithuman", "runtime bithuman"),
    ("fastapi", "fastapi"),
]:
    try:
        m = importlib.import_module(mod)
        versao = getattr(m, "__version__", "")
        print(f"  ok      {rotulo} {versao}")
    except Exception as exc:
        print(f"  FALHOU  {rotulo}: {type(exc).__name__}: {exc}")
PY
