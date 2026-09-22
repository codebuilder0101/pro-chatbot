#!/usr/bin/env bash
# Publica o token server em HTTPS atras do nginx que ja existe no VPS.
#
# Por que nginx e nao o Caddy do docker-compose.prod.yml: nesta maquina as
# portas 80/443 ja sao do nginx, que serve os outros sites. Subir um segundo
# servidor nelas nao funciona. Entao o dominio vira um vhost do nginx com
# certificado do Let's Encrypt via certbot, e o token server continua o mesmo
# processo systemd em 127.0.0.1:8099.
#
# Pre-requisitos:
#   - registro A do dominio apontando para este VPS (confira: getent ahostsv4 $DOMAIN)
#   - TOKEN_SERVER_DOMAIN definido no /var/www/pro-chatbot/.env
#
#     bash 07_nginx_tls.sh                 # le TOKEN_SERVER_DOMAIN do .env
#     bash 07_nginx_tls.sh chatbot.exemplo.com.br
set -euo pipefail

APP=/var/www/pro-chatbot
DOMAIN="${1:-$(grep -E '^TOKEN_SERVER_DOMAIN=' "$APP/.env" | cut -d= -f2 | tr -d ' \r' || true)}"
[ -n "$DOMAIN" ] || { echo "defina TOKEN_SERVER_DOMAIN no .env ou passe como argumento"; exit 1; }

echo "=== dominio: $DOMAIN ==="
MEU_IP=$(curl -s --max-time 10 https://api.ipify.org || true)
# getent existe em qualquer glibc; dig nem sempre esta instalado.
DNS_IP=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)
echo "ip deste VPS: ${MEU_IP:-?}   registro A: ${DNS_IP:-nenhum}"
if [ -n "$MEU_IP" ] && [ "$MEU_IP" != "$DNS_IP" ]; then
    echo "AVISO: o DNS nao aponta para este VPS; o certbot vai falhar ate propagar."
fi

echo
echo "=== certbot ==="
if ! command -v certbot >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends certbot python3-certbot-nginx
fi
echo "certbot: $(certbot --version 2>&1)"

echo
echo "=== vhost nginx ==="
# So' /health e /token existem. Qualquer outra rota e' 404 antes de chegar ao
# Python - mesma politica do Caddyfile.
cat > "/etc/nginx/sites-available/$DOMAIN" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location = /health {
        proxy_pass http://127.0.0.1:8099/health;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location = /token {
        proxy_pass http://127.0.0.1:8099/token;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 30s;
    }

    location / {
        return 404;
    }
}
NGINX
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
nginx -t
systemctl reload nginx
echo "vhost ativo em http://$DOMAIN"

echo
echo "=== certificado (Let's Encrypt) ==="
# --nginx reescreve o vhost acima com listen 443 + redirect 80->443.
# --redirect garante que HTTP em claro nunca chegue ao /token.
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect \
    --register-unsafely-without-email
systemctl reload nginx

echo
echo "=== prova ==="
sleep 2
curl -s --max-time 15 "https://$DOMAIN/health" || echo "sem resposta em https://$DOMAIN/health"
echo
echo
echo "renovacao automatica: $(systemctl is-enabled certbot.timer 2>/dev/null || echo 'confira: systemctl list-timers | grep certbot')"
echo
echo "Proximo passo: buildar o APK com"
echo "  -Piara.tokenServerUrl=https://$DOMAIN/ -Piara.tokenServerKey=<TOKEN_SERVER_SHARED_SECRET do .env>"
