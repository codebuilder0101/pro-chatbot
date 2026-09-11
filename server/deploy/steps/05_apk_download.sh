#!/usr/bin/env bash
# Servidor estatico temporario, so' para entregar o APK de teste.
#
# Serve APENAS /var/www/pro-chatbot/dist, numa porta propria. Nao encosta no
# nginx nem nas portas 80/443, que servem os sites em producao.
#
# E' temporario de proposito. Quando o APK ja estiver instalado nos aparelhos:
#     systemctl disable --now iara-apk
set -euo pipefail

PORT=8098

if ss -tln | grep -q ":$PORT "; then
    echo "porta $PORT ocupada; escolha outra"
    exit 1
fi

cat > /etc/systemd/system/iara-apk.service <<UNIT
[Unit]
Description=IARA - entrega temporaria do APK de teste
After=network.target

[Service]
Type=simple
WorkingDirectory=/var/www/pro-chatbot/dist
ExecStart=/usr/bin/python3 -m http.server $PORT --bind 0.0.0.0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now iara-apk
sleep 3

echo "estado: $(systemctl is-active iara-apk)"
echo
ls -la /var/www/pro-chatbot/dist
echo
curl -s -o /dev/null -w "local -> HTTP %{http_code}\n" "http://127.0.0.1:$PORT/IARA-arm64.apk"
