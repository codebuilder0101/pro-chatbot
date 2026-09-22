# IARA / Ayo — Fase 1

APK Android standalone com avatar falante em tempo real. O usuário abre o app,
fala pelo microfone e recebe a resposta de um avatar feminino com voz clonada e
boca sincronizada.

O raciocínio da IARA **não** fica neste repositório: o cérebro é o fluxo do n8n,
que já carrega a lógica clínica montada e validada. O agente aqui é encanamento
— ouvido, boca e rosto.

Fora do escopo desta fase: WhatsApp, Z API, Play Store, base de conhecimento,
painel administrativo.

---

## O que mudou em relação à especificação

**0. O n8n virou o cérebro, não o porteiro.**
A spec original previa um LLM dentro do pipeline e o n8n só na fase 2, chamando
o token server. Depois de o cliente confirmar que toda a lógica clínica já está
montada e validada no n8n, o LLM saiu do pipeline: a `AgentSession` é
construída **sem `llm=`** e o `llm_node` do agente foi substituído por uma
chamada HTTP ao webhook. Detalhes na seção [O cérebro é o n8n](#o-cérebro-é-o-n8n).

Os três pontos abaixo foram verificados contra a documentação oficial e
divergem do que o documento assumia. Nenhum deles muda a arquitetura, mas todos
mudam o código.

**1. "HeyGen Interactive Avatar" hoje se chama HeyGen LiveAvatar.**
Não existe plugin `livekit-plugins-heygen`. O plugin oficial é
`livekit-plugins-liveavatar`, e é ele que [`server/agent/avatar/heygen.py`](server/agent/avatar/heygen.py)
usa por dentro. O arquivo manteve o nome `heygen.py` porque é assim que o
cliente chama o produto. A premissa central da spec continua válida: os dois
motores publicam a faixa de vídeo dentro da mesma sala LiveKit, então trocar de
fornecedor é mudar `AVATAR_ENGINE` no `.env`.

**2. A API do LiveKit Agents mudou de forma incompatível.**
A versão atual (1.7.1) usa `AgentServer` + `@server.rtc_session` +
`session.start(room_options=room_io.RoomOptions(...))`. As versões 1.0 e 1.5
usavam `WorkerOptions(entrypoint_fnc=...)` e
`room_input_options`/`room_output_options`. Exemplos de blog e respostas de
fórum ainda mostram a API antiga; ela não funciona aqui. O `requirements.txt`
fixa `~=1.7.1` de propósito.

**3. Os nomes de variáveis de ambiente da spec não são os que os plugins leem.**
O plugin do ElevenLabs lê `ELEVEN_API_KEY`, não `ELEVENLABS_API_KEY`; o do
HeyGen lê `LIVEAVATAR_API_KEY`; o do bitHuman lê `BITHUMAN_API_SECRET`.
[`server/agent/config.py`](server/agent/config.py) aceita os nomes da spec e faz
o alias no boot, então o `.env` continua sendo o da especificação.

E um ponto do app: **AGP 9 traz o suporte a Kotlin embutido**, então o plugin
`org.jetbrains.kotlin.android` não pode ser aplicado — a build falha se ele
estiver lá. E o `livekit-android` depende de `com.github.davidliu:audioswitch`,
que só existe no JitPack; o repositório está declarado com escopo restrito a
esse grupo em [`android/settings.gradle.kts`](android/settings.gradle.kts).

---

## Arquitetura

```
[App Android]
   |  1. POST /token (https, header x-api-key)
   v
[Token Server FastAPI] --> { livekit_url, token, room }
   |
   |  2. app entra na sala e publica o microfone
   v
[LiveKit Cloud - sala]
   ^                          ^
   |  3. agente entra na      |  4. motor de avatar entra na
   |     mesma sala           |     mesma sala e publica VÍDEO
   |                          |
[Agente Python] ---- áudio do TTS ----> [HeyGen LiveAvatar / bitHuman]
   |
   +-- Deepgram STT (streaming, pt-BR)
   +-- ElevenLabs TTS (streaming, voz clonada)
   |
   +--> POST webhook ──> [n8n: o cérebro clínico] ──> texto da resposta
```

O rosto **não** é renderizado no aparelho. O motor de avatar entrega o vídeo
com o lip sync já casado ao áudio, e o app só assina a faixa. É isso que
elimina a necessidade de escrever código de viseme.

**Nenhuma chave de fornecedor existe dentro do APK.** Um APK é descompilável. O
único segredo embarcado é o do token server, e ele não abre nada além de um
pedido de sala com escopo mínimo e TTL de 25 minutos.

---

## O cérebro é o n8n

O agente não pensa. Ele transcreve, manda o texto para o webhook do n8n, recebe
a resposta pronta e entrega para a voz e para o avatar. A `AgentSession` é
construída sem `llm=` e [`IaraAgent.llm_node`](server/agent/pipeline.py)
substitui a chamada ao LLM por uma chamada HTTP.

### O contrato

**Requisição** — `POST` para `N8N_WEBHOOK_URL`, com `N8N_AUTH_HEADER`/`N8N_AUTH_TOKEN`
se configurados:

```json
{
  "session_id": "session-uuid",
  "room": "session-uuid",
  "user_id": "identidade do participante",
  "turn": 3,
  "locale": "pt-BR",
  "text": "o que a pessoa acabou de falar",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

`session_id` é o nome da sala, único por conversa — serve direto como chave de
memória do fluxo. Se o n8n já guarda a memória sozinho, `N8N_HISTORY_TURNS=0`
tira o histórico do payload.

**Resposta** — o parser aceita o que os nós finais do n8n costumam devolver,
sem exigir mudança no workflow:

| formato | exemplo |
|---|---|
| objeto com chave de texto | `{"reply": "..."}` — também `text`, `output`, `message`, `answer`, `response`, `content` |
| lista (Respond to Webhook) | `[{"output": "..."}]` |
| aninhado no `json` do item | `{"json": {"output": "..."}}` |
| string crua | `"..."` |
| `text/plain` | corpo sem JSON nenhum |

Campo opcional `end_session: true` encerra a conversa depois da fala — útil
quando o roteiro clínico chega ao fim.

Se a resposta não tiver texto aproveitável, a IARA fala `BRAIN_FAILURE_TEXT` em
vez de ler JSON em voz alta. [`tests/test_n8n_parse.py`](server/tests/test_n8n_parse.py)
cobre todos esses formatos e roda sem instalar nada.

#### A armadilha que custou um dia: o SDK exige um `llm=` mesmo com `llm_node` sobrescrito

Em `_user_turn_completed_task` o livekit-agents 1.7 faz, **antes** de chamar
o `llm_node`:

```python
elif self.llm is None:
    return  # skip response if no llm is set
```

Sem um `llm=` na `AgentSession`, o turno do usuário é descartado em silêncio:
transcreve, fecha o turno, e não responde nada. Nenhum erro, nenhum aviso. A
saudação continua funcionando, porque `say()` não passa por aí — o que torna
o sintoma enganoso.

A solução é [`N8nSentinelLLM`](server/agent/pipeline.py): um LLM de mentira
que satisfaz a verificação e levanta erro se algum dia for chamado. O
`dry_run.py` não pegou isso porque chamava o `llm_node` direto, sem o
pipeline do SDK. Foi o teste com áudio real na sala que revelou.

## O silêncio enquanto o fluxo pensa

Este é o ponto delicado, e é o que a conversa com o cliente já antecipou. O n8n
devolve a resposta **inteira**, não token a token. O TTS não tem como começar a
falar antes de o fluxo terminar de raciocinar, e um fluxo clínico com muitas
condições leva segundos. Nesse intervalo o avatar ficaria parado encarando a
pessoa — que é exatamente a sensação de travamento que se quer evitar.

A solução implementada tem duas janelas:

```
fala do usuário
   │
   ├─ 0,0s ──── requisição sai para o n8n
   │
   ├─ 0,7s ──── resposta ainda não chegou?
   │            → "Deixa eu ver aqui."  + flush imediato no TTS
   │
   ├─ 4,7s ──── ainda não chegou?
   │            → "Ainda estou verificando, já te respondo."
   │
   └─ chegou ── fala a resposta de verdade
```

Detalhes que fazem diferença:

- **Abaixo de `N8N_FILLER_AFTER_S` ninguém ouve frase de espera nenhuma.** Turno
  rápido soa como conversa normal. Ajustar esse valor para menos de ~0,5 s faz a
  IARA falar "deixa eu ver" por cima de uma resposta que já estava chegando.
- **O `FlushSentinel` é obrigatório.** Sem ele o texto da frase de espera fica no
  buffer do TTS aguardando o resto da geração — ou seja, não sairia som nenhum,
  que é justamente o problema que estamos resolvendo.
- **As frases não se repetem duas vezes seguidas.** Repetição é o que denuncia
  que a frase é automática.
- **As frases de espera não entram no histórico enviado ao n8n.** Elas são
  artifício de UX, não conversa clínica; o histórico é mantido dentro de
  [`N8nBrain`](server/agent/n8n.py), não lido do `ChatContext`.
- **Barge-in cancela a requisição ao n8n.** Se a pessoa interrompe, a task é
  cancelada e a chamada HTTP morre junto. Num fluxo com estado, deixar a
  requisição correr avançaria o passo errado.

### Abertura da conversa

`GREETING_MODE=local` fala uma linha fixa na hora — mais rápido. `=n8n` manda
`N8N_START_EVENT` ao fluxo e fala a resposta dele, o que faz sentido quando o
roteiro clínico define como a conversa começa, ao custo de uma ida ao n8n antes
da primeira palavra.

---

## Estrutura

```
server/
  agent/
    agent.py            entrypoint do LiveKit Agent, limites de sessão
    pipeline.py         STT + TTS + barge-in + enchimento de espera
    n8n.py              cliente do webhook (o cérebro)
    config.py           leitura e alias das variáveis de ambiente
    metrics.py          instrumentação de latência por turno
    avatar/
      base.py           interface AvatarEngine
      heygen.py         HeyGen LiveAvatar
      bithuman.py       bitHuman
      factory.py        único ponto que importa um motor concreto
    prompts/
      system_pt_br.md   persona da IARA
  token_server/
    main.py             FastAPI: POST /token, GET /health
  tests/
    test_n8n_parse.py   parser de resposta do n8n, sem dependências
    check_eleven_agent.py  agente do ElevenLabs Agents usado pelo LiveAvatar
  requirements.txt  .env.example  Dockerfile  docker-compose.yml

android/
  app/src/main/java/br/com/iara/chat/
    MainActivity.kt
    ui/          HomeScreen, CallScreen, EndScreen, AvatarVideo, theme
    data/        TokenApi (Retrofit)
    call/        RoomManager, CallForegroundService, CallState
```

---

## Rodando o backend

```bash
cd server
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # preencha as chaves

python -m agent.agent download-files           # baixa VAD e turn detector
python -m agent.agent dev                      # agente
uvicorn token_server.main:app --port 8080      # token server, outro terminal
```

Com Docker:

```bash
cd server && cp .env.example .env
docker compose up --build
```

Confira a configuração antes de gastar minuto de avatar:

```bash
curl localhost:8080/health
```

`GET /health` valida as credenciais do LiveKit, o webhook do n8n e o motor de
avatar selecionado — chave presente, avatar_id presente, plugin instalado,
arquivo `.imx` existente. Se algo estiver faltando, ele diz o quê.

Dois testes, com propósitos diferentes:

```bash
cd server
python tests/test_n8n_parse.py   # parser do n8n, sem instalar nada
python tests/dry_run.py          # o agente contra o SDK real, sem credencial
```

E um diagnóstico à parte, para o caminho sem código em que o LiveAvatar usa um
agente do ElevenLabs Agents como cérebro e voz (modo LITE):

```bash
python tests/check_eleven_agent.py agent_xxx        # lê e confere
python tests/check_eleven_agent.py agent_xxx --fix  # corrige os formatos de áudio
```

Confere os dois formatos de áudio que o LiveAvatar exige (`pcm_24000` na saída do
TTS **e** na entrada do usuário), o plano da conta e, o mais útil, lista as
conversas do agente com a origem de cada uma: uma sessão do LiveAvatar que
conectou de verdade aparece ali. Se a sessão foi aberta e nenhuma conversa
surgiu, o worker do LiveAvatar nem abriu o WebSocket — a falha é do lado do
LiveAvatar, não do microfone, da chave nem do agente (foi o caso em 18/09/2026;
o contorno é um voice agent nativo do LiveAvatar, modo FULL, com o mesmo prompt).

O `dry_run.py` sobe um webhook falso em `localhost`, constrói a `AgentSession`
de verdade e roda o `llm_node` — verifica que a frase de espera sai no tempo
certo, que não se repete, que o barge-in derruba a conexão HTTP com o n8n e que
uma falha vira frase falada em vez de vazar detalhe técnico. Nada sai da
máquina; nenhuma credencial é necessária.

### O host do agente precisa ser Linux se o motor for bitHuman

O pacote nativo `bithuman` publica wheel **apenas** para Linux x86_64, Linux
aarch64 e macOS 14+ ARM. Em Windows o `pip install` falha — e falha bem, com
uma mensagem explícita, em vez de instalar silenciosamente uma versão velha.
Não compila da fonte: o motor precisa de ONNX Runtime, HDF5, FFmpeg e uma
toolchain Rust que o pip não monta.

Na prática isso não muda nada, porque o [`Dockerfile`](server/Dockerfile) já é
Linux (`python:3.12-slim`). Só vale saber para não perder tempo tentando rodar
o agente direto no Windows — ali só via WSL2 ou container.

O HeyGen não tem essa restrição: ele renderiza inteiramente na nuvem e o plugin
é Python puro.

### Requisito de CPU no host do agente

O `livekit-agents` importa `livekit-local-inference`, um binário nativo que
**não roda em CPU anterior a ~2017** — num Xeon E3-1270 v3 (Haswell) qualquer
versão dele derruba o processo com segfault, e como o import acontece no nível
de pacote, nem `import livekit.agents` passa. Segfault não é capturável por
`try/except`: o processo morre inteiro.

Duas consequências práticas:

- Escolha uma máquina razoavelmente moderna para o agente. Uma VM de nuvem
  atual resolve; um servidor reaproveitado de 2014 não.
- O token server **não** importa plugin de avatar (a checagem de `/health` é
  rasa, só de configuração), justamente para que uma falha assim não derrube a
  emissão de tokens junto.

---

## Rodando o app

O app precisa saber onde está o token server. Passe por propriedade de projeto
(nunca comitada) em `~/.gradle/gradle.properties` ou na linha de comando:

```bash
cd android
./gradlew :app:assembleDebug \
  -Piara.tokenServerUrl=http://10.0.2.2:8080/ \
  -Piara.tokenServerKey=troque-isto
```

`10.0.2.2` é o host da máquina visto de dentro do emulador. Para aparelho
físico, use o IP da máquina na rede local. A URL **precisa terminar com barra**
— é `baseUrl` de Retrofit.

Cleartext HTTP só é permitido para `10.0.2.2`, `localhost` e `127.0.0.1`,
conforme [`network_security_config.xml`](android/app/src/main/res/xml/network_security_config.xml).
Em produção, HTTPS.

### APK assinado

```bash
keytool -genkeypair -v -keystore iara.jks -keyalg RSA -keysize 2048 \
  -validity 10000 -alias iara

./gradlew :app:assembleRelease \
  -Piara.storeFile=/caminho/iara.jks \
  -Piara.storePassword=... -Piara.keyAlias=iara -Piara.keyPassword=... \
  -Piara.tokenServerUrl=https://api.seudominio.com/ \
  -Piara.tokenServerKey=...
```

O `signingConfig` só é aplicado quando `iara.storeFile` está presente; sem ele
a build produz um APK não assinado, em vez de falhar.

O APK universal fica em torno de 45 MB por causa das bibliotecas nativas do
WebRTC nas quatro ABIs. Se o tamanho incomodar na entrega, `splits { abi }`
resolve — não foi ligado para manter um único arquivo instalável em qualquer
aparelho de teste.

---

## Os dois motores de avatar

`AVATAR_ENGINE` decide qual entra na sala. Trocar é mudar essa variável, nunca
refatorar — só [`avatar/factory.py`](server/agent/avatar/factory.py) importa um
motor concreto.

### bitHuman

Uma confusão de nomenclatura que custa tempo: **o que o console do bitHuman
chama de "Agent code" é o `avatar_id` do plugin, e chega na API deles como
`agent_id`**. Três nomes para a mesma coisa. Vai em `BITHUMAN_AVATAR_ID`.

```
AVATAR_ENGINE=bithuman
BITHUMAN_API_KEY=      # vira BITHUMAN_API_SECRET para o plugin
BITHUMAN_AVATAR_ID=    # o "Agent code" do console
BITHUMAN_MODEL=essence
```

`BITHUMAN_MODEL` não é cosmético: `essence` usa ações predefinidas e a sessão
roda em CPU; `expression` gera expressões dinâmicas mas faz o plugin pedir
`mode: "gpu"` ao bitHuman. Começar em `essence` evita descobrir um requisito de
plano no meio de um teste.

Existe ainda o modo local, com `BITHUMAN_MODEL_PATH` apontando para um `.imx`:
aí o modelo roda dentro do processo do agente e o gargalo passa a ser a CPU da
sua máquina, não a fatura do fornecedor.

#### Diagnóstico da conta, sem abrir sessão

Duas chamadas resolvem quase toda dúvida de configuração. Nenhuma das duas
gasta crédito.

**A chave é válida?**

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST https://auth.api.bithuman.ai/v1/runtime-tokens/request \
  -H "content-type: application/json" -H "api-secret: SUA_CHAVE" -d '{}'
```

`200` com token de runtime = boa. `401` = inválida.

**Quais agentes existem, e em que estado?** Este é o endpoint que vale ouro e
não aparece na documentação do plugin:

```bash
curl -s https://api.bithuman.ai/v1/agents -H "api-secret: SUA_CHAVE"
```

Devolve, para cada agente: `code` (o que vai em `BITHUMAN_AVATAR_ID`), `name`,
`model` (o modelo com que ele foi configurado), `language`, `status` e um
`model_status` por modelo suportado. É a forma mais rápida de descobrir se um
código está errado ou se o problema é outro.

#### Uma armadilha real: `essence` não serve para qualquer agente

O agente da IARA (`A05AFZ5346`) está configurado como **`expression-1`**, e é
por isso que `BITHUMAN_MODEL=expression` no `.env`.

Com `BITHUMAN_MODEL=essence` a sessão é recusada, mesmo o `/v1/agents`
reportando `essence-1: ready`. O erro que volta é enganoso:

```
MODEL_NOT_FOUND: model not found: /Volumes/moraga-store/figures/A05AFZ5346/model.imx
```

Parece problema de credencial ou de código de agente errado, e não é — é o modo
errado. Pior: em `expression` a API responde `avatar_session_started: true`
para **qualquer** `agent_id`, inclusive um inventado, porque valida de forma
assíncrona. Ou seja, nenhum dos dois modos dá um "código inválido" honesto.
Confira o código pelo `/v1/agents`, não pela resposta da sessão.

### HeyGen LiveAvatar

```
AVATAR_ENGINE=heygen
HEYGEN_API_KEY=        # vira LIVEAVATAR_API_KEY para o plugin
HEYGEN_AVATAR_ID=
```

Uma dúvida que aparece sempre: **a voz configurada no painel do HeyGen é
ignorada nesta arquitetura.** O plugin não tem sequer um parâmetro de voz — ele
recebe o áudio do ElevenLabs que o nosso agente gera (`agent.speak` com PCM em
base64) e sincroniza a boca em cima dele. O painel do HeyGen só manda no modo
em que o próprio HeyGen faz STT/LLM/TTS, que não é o nosso.

---

## Barge-in

É o item que mais quebra esse tipo de projeto, então ele está configurado
explicitamente em [`pipeline.py`](server/agent/pipeline.py), não deixado no
padrão:

```python
interruption={
    "mode": "vad",                      # corta pelo sinal de voz, sem esperar STT
    "min_duration": 0.2,
    "false_interruption_timeout": 1.2,
    "resume_false_interruption": True,  # tosse não deixa a IARA muda
    "discard_audio_if_uninterruptible": True,
}
```

`mode: "vad"` é o caminho mais curto para ficar abaixo dos 300 ms exigidos,
porque não espera a transcrição chegar. O preço é cortar em tosse e "aham" — daí
a retomada automática de falsa interrupção.

Do lado do app, o cancelamento de eco é o que impede o microfone de captar a
própria voz da IARA saindo do alto-falante e disparar barge-in sozinho, sem
parar. Ele está ligado em
[`RoomManager.kt`](android/app/src/main/java/br/com/iara/chat/call/RoomManager.kt)
em dois níveis: `LocalAudioTrackOptions` (WebRTC) e
`javaAudioDeviceModuleCustomizer` (AEC/NS do próprio aparelho). **Xiaomi e
Samsung se comportam de forma diferente aqui** — se um modelo específico ecoar,
é este o ponto de ajuste.

---

## Medição de latência

Cada turno emite uma linha JSON estruturada (`turn_metrics`), e o fim da sessão
emite um resumo (`session_summary`) com p50, p90 e máximo.

| campo | o que é |
|---|---|
| `t_speech_end_epoch` | instante absoluto do fim da fala, para cruzar com outros logs |
| `t_stt_final` | ms até a transcrição final |
| `t_llm_first_token` | ms até o primeiro texto entregue ao TTS — com o n8n, normalmente a frase de espera |
| `t_n8n_ms` | quanto o fluxo do n8n levou pensando |
| `filler_used` | se foi preciso encher o silêncio neste turno |
| `t_tts_first_byte` | ms até o primeiro byte de áudio |
| `t_avatar_first_frame` | ms até o avatar começar a aparecer falando |
| `t_total` | = `t_avatar_first_frame`, o número que decide entre os motores |
| `avatar_frame_source` | `video` (frame real) ou `agent_state` (proxy) |

Sobre `avatar_frame_source`: por padrão o marco do avatar vem do evento
`agent_state_changed → speaking`, que é um proxy barato. Com
`MEASURE_AVATAR_VIDEO=true`, o agente assina a faixa de vídeo e cronometra o
primeiro frame de verdade. Isso custa CPU (decodifica vídeo no processo do
agente), então **ligue para a comparação HeyGen × bitHuman e desligue depois**.
Comparar números com `avatar_frame_source` diferente não vale nada.

Leia `t_n8n_ms` junto com `t_total`: se `t_total` estourar 1,5 s e `t_n8n_ms`
dominar o número, o gargalo está no workflow do n8n, não no pipeline de voz.
São times diferentes e correções diferentes — sem esse campo, a discussão vira
adivinhação.

A proporção de `filler_used` é o outro número que importa. Se quase todo turno
precisa de frase de espera, o roteiro está lento demais para uma conversa por
voz, e vale otimizar o fluxo antes de mexer em qualquer outra coisa.

Para persistir em arquivo, defina `METRICS_LOG_PATH=metrics/turns.jsonl`.

---

## Marcos

- **M1** — app conecta, avatar aparece e fala uma frase fixa com a boca
  sincronizada. Critério: vídeo visível e áudio audível em aparelho real.
- **M2** — ciclo completo fala → transcrição → resposta → voz → avatar. Critério:
  três turnos seguidos sem travar, barge-in cortando em menos de 300 ms.
- **M3** — desempenho: `t_total` abaixo de 1,5 s em 4G; desvio áudio/boca abaixo
  de 100 ms; sessão de 20 min sem queda; 5 sessões simultâneas; reconexão após
  10 s sem rede.
- **M4** — APK assinado, testado em três aparelhos de faixas diferentes, mais o
  comparativo HeyGen × bitHuman com números medidos
  ([`docs/comparativo-avatares.md`](docs/comparativo-avatares.md)).

---

## Estado atual

**Verificado por execução:**

- `./gradlew :app:assembleDebug` e `:app:assembleRelease` passam. Release com R8
  e `shrinkResources` ligados, regras de ProGuard incluídas para as classes que
  o WebRTC carrega por reflexão.
- Versões de todas as dependências conferidas nos repositórios em 03/09/2026.
- APIs do LiveKit (Agents 1.7.1 e Android 2.18.2) conferidas contra a
  documentação e o código-fonte do SDK.

- O app roda de verdade no emulador: entra na sala LiveKit, publica o
  microfone, renderiza vídeo remoto no recorte circular, muda, reconecta após
  perda de rede e encerra liberando o microfone. Verificado contra um
  `livekit-server --dev` local.
- O **token server é o de verdade**, não um mock: FastAPI rodando, `/health`
  respondendo, `401` sem a chave e com a chave errada, e o JWT emitido carrega
  exatamente os grants mínimos (`roomJoin`, `canPublish`, `canSubscribe`, sem
  `roomAdmin` nem `roomCreate`). O app do emulador conectou através dele.
- O **agente roda contra o SDK 1.7.1 instalado**: 26 de 26 verificações do
  `dry_run.py`, incluindo a `AgentSession` construída sem `llm=`, a frase de
  espera saindo em 0,41 s com o limite em 0,4 s, a segunda frase para fluxo
  longo, a ausência de repetição, o barge-in derrubando a conexão com o n8n, e
  o histórico enviado sem as frases de espera.
- O parser de resposta do n8n passa em 22 casos (`tests/test_n8n_parse.py`).

**Não verificado:** o agente dentro de uma sessão LiveKit real. O `dry_run.py`
exercita o `llm_node`, os plugins e a montagem da sessão, mas não há sala, não
há áudio e o STT/TTS nunca são chamados — isso depende das credenciais. O
detector de fim de turno da LiveKit Inference e o VAD nativo também ficam de
fora nesta máquina, pelo problema de CPU descrito acima.

**Não testado com o fluxo real:** o contrato com o n8n foi projetado para
aceitar os formatos usuais, mas o workflow do cliente ainda não respondeu uma
vez sequer. Primeira coisa a fazer quando houver acesso: apontar
`N8N_WEBHOOK_URL` para ele e conferir se o parser aceita a resposta.

**Não medido:** lip sync, latência de turno, sessão de 20 min e 5 sessões
simultâneas. Dependem das credenciais reais (LiveKit, Deepgram, ElevenLabs com
a voz clonada, HeyGen ou bitHuman com o avatar do cliente).

---

## Riscos que continuam de pé

- **Custo por minuto.** A renderização do avatar é cobrada mesmo com ele calado.
  Os limites de sessão (20 min, 90 s de silêncio) estão implementados em
  [`agent.py`](server/agent/agent.py) e cortam o pior caso — a sessão esquecida
  aberta. Pausar a renderização *entre turnos* dentro de uma sessão ativa não
  foi implementado: interromper e retomar o motor a cada turno acrescenta
  latência de religamento justamente no ponto que M3 mede. Vale medir o custo
  real antes de pagar esse preço.
- **Latência do fluxo clínico.** Este é agora o maior risco do M3. Um fluxo com
  muitas condições pode levar vários segundos, e nenhuma otimização do lado da
  voz compensa isso — a frase de espera disfarça, não conserta. Meça `t_n8n_ms`
  desde o primeiro dia. Se a mediana passar de ~1 s, a conversa deixa de soar
  natural por mais bem feito que esteja o resto.
- **Estado do fluxo e barge-in.** Quando a pessoa interrompe, a requisição é
  cancelada do nosso lado, mas o n8n pode já ter avançado o passo. Se o roteiro
  tem estado por sessão, vale o fluxo tolerar receber o mesmo turno de novo.
- **Rede móvel.** Testar sempre em 4G real, nunca só em wi-fi. O comportamento é
  outro, e é o cenário do critério de M3.
- **Áudio por fabricante.** Reservar tempo para Xiaomi e Samsung.
