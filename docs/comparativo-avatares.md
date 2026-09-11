# HeyGen LiveAvatar × bitHuman — comparativo

Documento de decisão do M4. **Preencher com números medidos, não com
impressões.** A pergunta que ele responde é uma só: qual motor entra em
produção.

## Como medir

Rode a mesma bateria nos dois motores, trocando apenas `AVATAR_ENGINE` no
`.env`. Nada mais pode mudar entre as duas rodadas — nem a voz, nem o modelo do
LLM, nem a rede.

```bash
# rodada 1
AVATAR_ENGINE=heygen MEASURE_AVATAR_VIDEO=true \
  METRICS_LOG_PATH=metrics/heygen.jsonl python -m agent.agent start

# rodada 2
AVATAR_ENGINE=bithuman MEASURE_AVATAR_VIDEO=true \
  METRICS_LOG_PATH=metrics/bithuman.jsonl python -m agent.agent start
```

`MEASURE_AVATAR_VIDEO=true` nas duas. Comparar uma rodada com
`avatar_frame_source: video` contra outra com `agent_state` não mede nada.

Bateria mínima por motor:

- 30 turnos de conversa normal, em 4G real, em aparelho físico
- 10 barge-ins deliberados (cortar a IARA no meio da frase)
- 1 sessão de 20 minutos ininterrupta
- 5 sessões simultâneas

Extração dos números:

```bash
# p50 e p90 de t_total
python - <<'PY'
import json, statistics as st
for engine in ("heygen", "bithuman"):
    vals = [
        j["t_total"]
        for line in open(f"metrics/{engine}.jsonl", encoding="utf-8")
        if (j := json.loads(line)).get("t_total") is not None
    ]
    vals.sort()
    if not vals:
        print(engine, "sem dados")
        continue
    print(
        engine,
        "n=", len(vals),
        "p50=", round(st.median(vals)),
        "p90=", round(vals[int(len(vals) * 0.9) - 1]),
        "max=", round(vals[-1]),
    )
PY
```

## Latência (ms, medido)

| métrica | HeyGen | bitHuman | critério M3 |
|---|---|---|---|
| `t_stt_final` p50 | | | — |
| `t_llm_first_token` p50 | | | — |
| `t_tts_first_byte` p50 | | | — |
| `t_avatar_first_frame` p50 | | | — |
| **`t_total` p50** | | | **< 1500** |
| `t_total` p90 | | | — |
| `t_total` máximo | | | — |
| corte de barge-in p50 | | | **< 300** |

## Qualidade

Aqui a impressão vale, mas escrita e datada, não lembrada.

| item | HeyGen | bitHuman |
|---|---|---|
| desvio percebido áudio/boca (< 100 ms?) | | |
| fidelidade ao rosto de referência | | |
| naturalidade em pt-BR (fonemas nasais, "ão", "lh") | | |
| comportamento no silêncio entre turnos | | |
| artefatos visíveis em 4G | | |

## Operação e custo

| item | HeyGen LiveAvatar | bitHuman |
|---|---|---|
| onde renderiza | nuvem do fornecedor | processo do agente |
| modelo de cobrança | por minuto de sessão | licença + CPU própria |
| custo de 5 sessões × 20 min | | |
| CPU/RAM por sessão no agente | ~0 | |
| custo de infra para 5 simultâneas | | |
| tempo de entrada na sala (cold start) | | |
| comportamento ao perder rede 10 s | | |
| limite de sessões simultâneas do plano | | |

`bithuman` roda o modelo localmente, então o gargalo dele é a máquina do
agente, não a fatura do fornecedor. `heygen` é o inverso. Isso muda o cálculo de
escala: com bitHuman, a quinta sessão simultânea pode exigir uma máquina maior;
com HeyGen, exige um plano maior.

## Decisão

**Motor escolhido:**

**Data:**

**Justificativa (citando os números acima):**

**O que faria mudar de ideia:**
