#!/usr/bin/env bash
# Registra o token server como servico systemd.
#
# Segue a convencao desta maquina: processo nativo com venv proprio, como os
# outros projetos em /var/www. Nao usa Docker, nao encosta no nginx e nao
# disputa as portas 80/443, que servem os sites em producao.
#
# O agente NAO vira servico ainda: sem DEEPGRAM_API_KEY e sem N8N_WEBHOOK_URL
# ele subiria so' para ficar reiniciando em laco. Entra quando as chaves
# chegarem.
set -euo pipefail

APP=/var/www/pro-chatbot

cat > /etc/systemd/system/iara-token-server.service <<'UNIT'
[Unit]
Description=IARA - token server (emite token de sala para o app)
After=network.target livekit-server.service
Wants=livekit-server.service

[Service]
Type=simple
WorkingDirectory=/var/www/pro-chatbot
EnvironmentFile=/var/www/pro-chatbot/.env
ExecStart=/var/www/pro-chatbot/.venv/bin/uvicorn token_server.main:app --host 0.0.0.0 --port 8099
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now iara-token-server
sleep 3

echo "=== estado ==="
systemctl is-active iara-token-server
echo
ss -tlnp | grep ":8099" || echo "AVISO: 8099 nao esta escutando"
echo
echo "=== /health local ==="
curl -s --max-time 10 http://127.0.0.1:8099/health || echo "sem resposta"
echo
echo
echo "=== ultimas linhas do log ==="
journalctl -u iara-token-server -n 8 --no-pager | tail -8
