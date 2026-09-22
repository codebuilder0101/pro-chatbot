#!/usr/bin/env bash
# Troca o worker de demonstracao pelo agente de producao.
#
# Diferencas que importam:
#   iara-m1     registra SEM agent_name -> o LiveKit despacha para qualquer
#               sala nova. Bom para demonstrar, errado em producao.
#   iara-agent  registra COM agent_name=iara -> so entra quando o token
#               server pede. Quem decide e' o token server.
#
# Os dois juntos brigariam pela mesma sala, entao o de demonstracao sai.
#
# Tambem reescreve a unit do token server: ele passa a escutar so' em
# 127.0.0.1, porque quem fala com a internet e' o nginx com TLS
# (07_nginx_tls.sh). Antes ele ficava em 0.0.0.0:8099, em HTTP puro.
#
# Idempotente: pode rodar de novo a cada deploy.
set -euo pipefail

APP=/var/www/pro-chatbot
cd "$APP"

echo "=== conferindo o .env ==="
[ -f .env ] || { echo "faltou $APP/.env"; exit 1; }
if [ -f .env.local ]; then
    # .env.local e' do emulador (ws://10.0.2.2) e VENCE o .env. Em producao
    # nao pode existir.
    rm -f .env.local
    echo "removido .env.local (config de emulador)"
fi
for v in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET DEEPGRAM_API_KEY \
         ELEVENLABS_API_KEY ELEVENLABS_VOICE_ID N8N_WEBHOOK_URL \
         TOKEN_SERVER_SHARED_SECRET AGENT_HTTP_PORT; do
    val="$(grep -E "^$v=" .env | head -1 | cut -d= -f2- || true)"
    if [ -z "$val" ]; then echo "faltou $v no .env"; exit 1; fi
done
if grep -qE '^TOKEN_SERVER_SHARED_SECRET=troque-isto' .env; then
    echo "TOKEN_SERVER_SHARED_SECRET ainda e' o placeholder"; exit 1
fi
# systemd EnvironmentFile nao tira comentario depois do valor: "X=1  # nota"
# vira o valor "1  # nota". Barra antes que vire bug silencioso.
if grep -vE '^\s*(#|$)' .env | grep -qE '=.*\s#'; then
    echo "ha comentario na mesma linha de um valor no .env; mova para a linha de cima:"
    grep -nvE '^\s*(#|$)' .env | grep -E '=.*\s#'
    exit 1
fi
chmod 600 .env
echo "ok"

echo
echo "=== arquivos dos plugins (idempotente) ==="
# TURN_DETECTOR=multilingual precisa do modelo local; `inference` usa o modelo
# hospedado pela LiveKit e nao. Baixar nao faz mal e cobre a troca de modo,
# mas uma falha aqui (rede, plugin sem download) nao pode travar o deploy.
./.venv/bin/python -m livekit.agents download-files 2>&1 | tail -4     || echo "AVISO: download-files falhou; so' importa se TURN_DETECTOR=multilingual"

echo
echo "=== desligando o worker de demonstracao ==="
systemctl disable --now iara-m1 2>/dev/null || true
echo "iara-m1: $(systemctl is-active iara-m1 2>/dev/null || echo inactive)"

echo
echo "=== token server (so' localhost; o nginx faz o TLS) ==="
cat > /etc/systemd/system/iara-token-server.service <<'UNIT'
[Unit]
Description=IARA - token server (emite token de sala para o app)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/var/www/pro-chatbot
EnvironmentFile=/var/www/pro-chatbot/.env
ExecStart=/var/www/pro-chatbot/.venv/bin/uvicorn token_server.main:app --host 127.0.0.1 --port 8099
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

echo
echo "=== agente de producao ==="
cat > /etc/systemd/system/iara-agent.service <<'UNIT'
[Unit]
Description=IARA - agente de producao (ouve, fala com o n8n, move o avatar)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/var/www/pro-chatbot
EnvironmentFile=/var/www/pro-chatbot/.env
ExecStart=/var/www/pro-chatbot/.venv/bin/python -m agent.agent start
Restart=always
RestartSec=5
# o SDK encerra as sessoes em andamento antes de sair; dar tempo a ele
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable iara-token-server iara-agent >/dev/null
systemctl restart iara-token-server
systemctl restart iara-agent
sleep 12

echo
echo "=== estado ==="
for s in nginx iara-token-server iara-agent iara-m1; do
    printf "  %-20s %s\n" "$s" "$(systemctl is-active $s 2>/dev/null || echo inactive)"
done

echo
echo "=== portas ==="
ss -tlnp | grep -E ":(8100|8099) " || echo "AVISO: 8100 (agente) / 8099 (token server) nao estao escutando"

echo
echo "=== o worker registrou no LiveKit? ==="
journalctl -u iara-agent -n 120 --no-pager \
    | grep -oE "registered worker[^|]*|agent_name\": \"[a-z]*\"|Traceback|Error[^\"]*|address already in use" \
    | tail -4 || true

echo
echo "=== /health (local) ==="
curl -s --max-time 8 http://127.0.0.1:8099/health || echo "sem resposta"
echo
