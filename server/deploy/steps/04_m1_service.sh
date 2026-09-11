#!/usr/bin/env bash
# Deixa o worker do M1 rodando como servico, para a demonstracao continuar de
# pe depois que o terminal fechar.
#
# Isto e' um servico de DEMONSTRACAO, nao o agente de producao. Ele registra
# sem `agent_name`, o que faz o LiveKit despachar para qualquer sala nova -
# util agora, errado depois. Quando o agente de verdade entrar (com Deepgram e
# n8n), desligue este:
#     systemctl disable --now iara-m1
set -euo pipefail

pkill -f "tests/m1_agent.py" 2>/dev/null || true

cat > /etc/systemd/system/iara-m1.service <<'UNIT'
[Unit]
Description=IARA - worker de demonstracao do M1 (avatar fala frase fixa)
After=network.target livekit-server.service
Wants=livekit-server.service

[Service]
Type=simple
WorkingDirectory=/var/www/pro-chatbot
EnvironmentFile=/var/www/pro-chatbot/.env
ExecStart=/var/www/pro-chatbot/.venv/bin/python tests/m1_agent.py start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now iara-m1
sleep 8

echo "=== servicos do projeto ==="
for s in livekit-server iara-token-server iara-m1; do
    printf "  %-20s %s\n" "$s" "$(systemctl is-active $s)"
done

echo
echo "=== o worker registrou? ==="
journalctl -u iara-m1 -n 40 --no-pager | grep -iE "registered worker|error|Traceback" | tail -3
