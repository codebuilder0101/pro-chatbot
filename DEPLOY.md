# Subir o backend no VPS Linux

## Como está no ar (22/09/2026)

| peça | onde |
|---|---|
| VPS | `161.97.77.100` (Ubuntu 24.04, compartilhado com outros sites), app em `/var/www/pro-chatbot` |
| token server | `https://chatbot.michaelhassan.dev` → nginx (TLS Let's Encrypt, renova sozinho) → `127.0.0.1:8099` (systemd `iara-token-server`) |
| agente | systemd `iara-agent`, `agent_name=iara`, saúde em `127.0.0.1:8100` |
| LiveKit | LiveKit Cloud `wss://chatbot-uvygbkun.livekit.cloud` (o `livekit-server` local do VPS não é mais usado) |
| avatar | HeyGen LiveAvatar, avatar "IARA AYO CORP 2" |
| cérebro | `https://webhookprod.iara.ia.br/webhook/iara-app-voz` |

Redeploy = `bundle.sh` na sua máquina, enviar o tarball, extrair sobre
`/var/www/pro-chatbot`, e rodar `deploy/steps/06_agent_prod.sh`. O `.env` fica
só no VPS (`chmod 600`); o passo 06 valida as chaves e recusa `.env` com
comentário na mesma linha do valor (o systemd não os ignora). O passo
`07_nginx_tls.sh` só precisa rodar de novo se o domínio mudar.

O APK de produção é buildado com
`-Piara.tokenServerUrl=https://chatbot.michaelhassan.dev/ -Piara.tokenServerKey=<TOKEN_SERVER_SHARED_SECRET do .env do VPS>`.

---

O que vai para o VPS é **só a pasta `server/`**. O `android/` fica na sua
máquina — dele sai um APK que só precisa saber a URL do token server. A pasta
`assets/` também fica: as imagens já viraram recursos dentro do APK.

---

## Por que o VPS resolve dois bloqueios de uma vez

**O bitHuman não roda em Windows.** O pacote nativo só publica wheel para Linux
x86_64, Linux aarch64 e macOS ARM. No VPS Linux instala normalmente.

**O worker do bitHuman precisa alcançar o LiveKit.** Ele entra na sala a partir
da nuvem deles, usando a URL que o nosso agente manda. Um `ws://127.0.0.1:7880`
na sua máquina é invisível para eles; um endereço público não é.

---

## 1. Empacotar

Na sua máquina, na raiz do repositório:

```bash
bash server/deploy/bundle.sh
```

Sai um `iara-server.tar.gz` de ~32 KB. O script exclui de propósito:

| não vai | por quê |
|---|---|
| `server/.venv/` | 584 MB de dependências compiladas para Windows, inúteis no Linux |
| `server/.env` | segredo não viaja em tarball — você cria o dele no VPS |
| `server/.env.local` | **este é o perigoso**: aponta para `ws://10.0.2.2:7880` e tem chaves `dev`. Ele é lido *antes* do `.env` e vence. Se for junto, o agente em produção tenta falar com o emulador Android que não existe lá |
| `__pycache__/` | bytecode de outro sistema |

Envie:

```bash
scp iara-server.tar.gz usuario@SEU_VPS:/tmp/
ssh usuario@SEU_VPS
sudo mkdir -p /opt/iara && sudo chown $USER /opt/iara
tar -xzf /tmp/iara-server.tar.gz -C /opt/iara
```

---

## 2. Escolher onde fica o LiveKit

### Opção A — LiveKit Cloud (recomendada para começar)

Menos peças, e resolve sozinho TLS, TURN e as faixas de UDP que costumam
brigar com firewall de VPS. Crie um projeto em `cloud.livekit.io`, pegue
`LIVEKIT_URL`, `LIVEKIT_API_KEY` e `LIVEKIT_API_SECRET`, e siga para o passo 3.

Nada de LiveKit roda no seu VPS nesse caminho.

### Opção B — LiveKit no próprio VPS

Use o gerador oficial, que já produz config, TLS e TURN:

```bash
docker run --rm -it -v$PWD:/output livekit/generate
```

Ele pergunta o domínio e gera `livekit.yaml`, `docker-compose.yaml`,
`caddy.yaml` e `redis.conf`.

**Atenção ao conflito de portas.** O compose gerado pelo LiveKit sobe um Caddy
que ocupa as portas 80 e 443. O nosso
[`docker-compose.prod.yml`](server/docker-compose.prod.yml)
também sobe um Caddy nas mesmas portas. Os dois juntos não sobem.

Escolha um:

- **mais simples:** remova o serviço `caddy` do *nosso* compose e acrescente o
  domínio do token server ao `caddy.yaml` do LiveKit, apontando para
  `token-server:8080`;
- ou deixe cada stack numa rede/IP próprio.

Portas que o firewall precisa abrir nesta opção: TCP 80, 443 e 7881; UDP 3478
e 50000–60000.

---

## 3. Criar o `.env` no VPS

```bash
cd /opt/iara/server
cp .env.example .env
nano .env
```

O que já está confirmado e pode entrar como está:

```dotenv
# HeyGen LiveAvatar (chave e avatar validados em 21/09/2026 com tests/check_liveavatar.py)
AVATAR_ENGINE=heygen
HEYGEN_API_KEY=                 # a mesma do server/.env desta maquina
HEYGEN_AVATAR_ID=b0b577bd-bdaf-4490-ab6c-f24f10df1c44   # "IARA AYO CORP 2"
HEYGEN_VIDEO_QUALITY=high

# bitHuman, se precisar voltar: AVATAR_ENGINE=bithuman
BITHUMAN_API_KEY=DzBUCEPWyqQUeWeHxy31xof2gMKipRoiSYvYP5CLQsEJuaOXFop3PwjXSXLGhCNfa
BITHUMAN_AVATAR_ID=A05AFZ5346
BITHUMAN_MODEL=expression

ELEVENLABS_API_KEY=sk_...
ELEVENLABS_VOICE_ID=bgFrKEhyj6QhB4Os9iaa
```

**Com `AVATAR_ENGINE=heygen` o `LIVEKIT_URL` precisa ser `wss://` público.**
O worker do LiveAvatar roda na nuvem deles e entra na sala como participante;
um LiveKit em `localhost`/`10.0.2.2` cria a sessão, responde 200 no `/start`
e nunca publica vídeo. Depois de preencher o `.env`, confira com:

```bash
.venv/bin/python tests/check_liveavatar.py            # chave, avatar, LIVEKIT_URL — sem gastar crédito
.venv/bin/python tests/check_liveavatar.py --session  # abre uma sessão real de alguns segundos (cobra)
```

O que ainda falta conseguir:

```dotenv
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
N8N_WEBHOOK_URL=

TOKEN_SERVER_SHARED_SECRET=   # invente um: openssl rand -hex 32
TOKEN_SERVER_DOMAIN=          # ex.: api.suaempresa.com.br
```

O `TOKEN_SERVER_DOMAIN` precisa ter um registro A apontando para o IP do VPS
**antes** de subir, senão o Caddy não consegue emitir o certificado.

Trave as permissões:

```bash
chmod 600 .env
```

---

## 4. Subir

```bash
cd /opt/iara/server
docker compose -f docker-compose.prod.yml up -d --build
```

A primeira build leva alguns minutos: instala `livekit-agents`, os plugins e o
runtime do bitHuman, e baixa os pesos do VAD.

Conferir:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f agent

curl https://SEU_DOMINIO/health
```

O `/health` responde algo assim quando está tudo de pé:

```json
{"ok":true,"avatar":{"engine":"bithuman","ok":true,"detail":"model=expression"},
 "cerebro":{"n8n":true},"problemas":[]}
```

Se `ok` vier `false`, o array `problemas` diz exatamente o que falta.

---

## 5. Apontar o APK para o VPS

Na sua máquina:

```bash
cd android
./gradlew :app:assembleRelease \
  -Piara.tokenServerUrl=https://SEU_DOMINIO/ \
  -Piara.tokenServerKey=O_MESMO_TOKEN_SERVER_SHARED_SECRET \
  -Piara.storeFile=/caminho/iara.jks \
  -Piara.storePassword=... -Piara.keyAlias=iara -Piara.keyPassword=...
```

A URL **precisa terminar com barra** — é `baseUrl` de Retrofit. E precisa ser
`https://`: o app só aceita HTTP em claro para `10.0.2.2` e `localhost`, que é
o emulador.

---

## Dimensionamento do VPS

O bitHuman renderiza o avatar **na nuvem deles**, não no seu VPS — o
`mode: "gpu"` do modelo `expression` fala do backend deles. **Você não precisa
de GPU.**

O que roda no VPS é o encanamento: áudio entrando, STT, chamada ao n8n, TTS,
áudio saindo. Ponto de partida razoável para as 5 sessões da fase 1: **2 vCPU e
4 GB**. Trate como chute inicial — meça `t_total` e `t_n8n_ms` antes de fixar.

Uma restrição herdada de um problema real: o `livekit-agents` importa
`livekit-local-inference`, um binário nativo que **não roda em CPU anterior a
~2017** (num Xeon Haswell aqui ele derruba o processo com segfault, e o import
acontece no nível de pacote, então nem `import livekit.agents` passa). Qualquer
VPS atual serve; um plano baseado em hardware muito antigo, não.

---

## Onde os arquivos ficam

```
/opt/iara/
  server/
    .env                        <- você cria aqui, nunca vem no tarball
    agent/  token_server/  tests/
    Dockerfile  requirements.txt
    docker-compose.prod.yml
    deploy/
      Caddyfile
  livekit/                      <- só na Opção B, gerado por livekit/generate
```

---

## Verificação rápida no VPS

Estes dois rodam sem instalar nada além do que o container já tem:

```bash
docker compose -f docker-compose.prod.yml exec agent python tests/test_n8n_parse.py
docker compose -f docker-compose.prod.yml exec agent python tests/dry_run.py
```

O `dry_run.py` sobe um webhook falso em `localhost` e exercita o `llm_node` de
verdade: frase de espera no tempo certo, barge-in cancelando a chamada ao n8n,
falha virando frase falada. Nada sai da máquina.

E para conferir a conta do bitHuman a qualquer momento, sem gastar crédito:

```bash
curl -s https://api.bithuman.ai/v1/agents -H "api-secret: SUA_CHAVE"
```

---

## Códigos de acesso (desde 30/09/2026)

O segredo que o APK carrega no header `x-api-key` é extraível: basta
descompilar o arquivo. Enquanto ele foi o único controle, qualquer pessoa com
o APK abria conversa e queimava minutos pagos de avatar. O **código de acesso**
fecha isso sem exigir cadastro: ele não existe dentro do binário, é digitado
pela pessoa, fica guardado só no aparelho dela e pode ser revogado no servidor
sem republicar o app.

### Como os minutos são controlados

O token server não sabe quando a conversa termina, então contar depois seria
furado. O controle é por **reserva**:

1. ao emitir o token, debita o pior caso (`SESSION_MAX_MINUTES`) do saldo do código;
2. quando o agente encerra, ele chama `/session-ended` e a diferença volta.

Se o agente morrer e nunca avisar, o pior caso continua debitado. Erra para o
lado seguro, que é o único aceitável quando o erro custa dinheiro.

### Administrar os códigos

Os endpoints `/admin/codes` respondem **apenas em 127.0.0.1** e não são
publicados pelo nginx. Use a ferramenta, da sua máquina:

```bash
python deploy/codes.py listar
python deploy/codes.py criar "Clinica Exemplo" --teto 600 --validade 2026-12-31
python deploy/codes.py desativar ABCD2345
python deploy/codes.py ativar ABCD2345
python deploy/codes.py remover ABCD2345
```

`access_codes.json` no VPS é a fonte da verdade, inclusive do consumo
acumulado. **Faça backup dele.**

### O que isso muda no app

A primeira tela passou a pedir o código. Digita uma vez e fica guardado. Se o
servidor recusar, o app apaga o código e volta para a digitação, em vez de
insistir com um código morto.
