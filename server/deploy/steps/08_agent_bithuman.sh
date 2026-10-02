#!/usr/bin/env bash
# Sobe um SEGUNDO worker, rodando com o bitHuman, lado a lado com o de producao.
#
# Para que serve: o motor de avatar e' configuracao do servidor, nao do app.
# Sem isto, comparar LiveAvatar e bitHuman exigiria trocar o AVATAR_ENGINE e
# reiniciar entre cada teste, o que impede o cliente de ver os dois no mesmo
# dia, no mesmo aparelho, com a mesma conversa.
#
# Com os dois no ar, o app diz qual quer no pedido do token e o token server
# despacha para o worker certo:
#   iara             AVATAR_ENGINE=heygen    (LiveAvatar, o padrao)
#   iara-bithuman    AVATAR_ENGINE=bithuman
#
# O .env NAO muda: este servico sobrescreve so' as duas variaveis que importam.
# Assim o worker de producao continua exatamente como esta.
#
# Custa dinheiro ter os dois ligados? Nao por estar ligado. Os dois so' gastam
# quando ha conversa, e cada conversa usa um motor so'.
#
# Para desligar quando a comparacao acabar:
#   systemctl disable --now iara-agent-bithuman
set -euo pipefail

APP=/var/www/pro-chatbot
cd "$APP"

[ -f .env ] || { echo "faltou $APP/.env"; exit 1; }

echo "=== conferindo a configuracao do bitHuman ==="
for v in BITHUMAN_API_KEY BITHUMAN_AVATAR_ID; do
    val="$(grep -E "^$v=" .env | head -1 | cut -d= -f2- || true)"
    if [ -z "$val" ]; then echo "faltou $v no .env"; exit 1; fi
done
echo "avatar bitHuman: $(grep -E '^BITHUMAN_AVATAR_ID=' .env | cut -d= -f2-)"

# Porta propria para o endpoint de saude. A do worker de producao (8100) ja
# esta ocupada, e duas portas iguais derrubam o segundo com "address in use".
PORTA=8101

echo
echo "=== servico ==="
cat > /etc/systemd/system/iara-agent-bithuman.service <<UNIT
[Unit]
Description=IARA - worker alternativo com avatar bitHuman (comparacao)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
# As tres variaveis que mudam vao na linha de comando, e NAO em Environment=.
# Motivo: no systemd o EnvironmentFile sobrescreve o Environment, nao o
# contrario. Com Environment= o worker herdava AGENT_HTTP_PORT=8100 do .env,
# batia de frente com o worker de producao e morria em laco com
# "address already in use". Variavel na linha de comando sempre vence.
ExecStart=/usr/bin/env AVATAR_ENGINE=bithuman AGENT_NAME=iara-bithuman     AGENT_HTTP_PORT=$PORTA $APP/.venv/bin/python -m agent.agent start
Restart=always
RestartSec=5
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable iara-agent-bithuman >/dev/null
systemctl restart iara-agent-bithuman
sleep 14

echo
echo "=== estado dos dois workers ==="
for s in iara-agent iara-agent-bithuman; do
    printf "  %-24s %s\n" "$s" "$(systemctl is-active $s 2>/dev/null || echo inactive)"
done

echo
echo "=== portas de saude ==="
ss -tlnp | grep -E ":(8100|$PORTA) " || echo "AVISO: 8100 e/ou $PORTA nao estao escutando"

echo
echo "=== os dois registraram no LiveKit? ==="
for s in iara-agent iara-agent-bithuman; do
    nome=$(journalctl -u $s --since "2 min ago" --no-pager -o cat \
        | grep -oE '"agent_name": "[a-z-]+"' | tail -1)
    printf "  %-24s %s\n" "$s" "${nome:-nao registrou ainda}"
done
