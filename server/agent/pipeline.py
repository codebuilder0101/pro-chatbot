"""Montagem do pipeline de voz: STT -> n8n -> TTS, com barge-in.

Diferenca importante em relacao a um agente de voz comum: nao ha LLM no
pipeline. O cerebro da IARA e' o fluxo do n8n, que ja carrega toda a logica
clinica. A AgentSession e' construida sem `llm=` e o `llm_node` do Agent e'
substituido por uma chamada HTTP ao webhook.

Isso tem um preco que precisa estar explicito: o n8n devolve a resposta
inteira, nao token a token. O TTS nao consegue comecar a falar antes de o
fluxo terminar de pensar. Por isso existe o enchimento de espera aqui embaixo
- nao e' enfeite, e' o que impede o avatar de ficar parado encarando a pessoa
enquanto o fluxo roda.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterable, Callable
from pathlib import Path
from typing import Any

from livekit.agents import (
    Agent,
    AgentSession,
    FlushSentinel,
    ModelSettings,
    TurnHandlingOptions,
    llm,
)
from livekit.plugins import deepgram, elevenlabs, silero

from .config import settings
from .n8n import BrainError, BrainReply, N8nBrain

# Importar aqui registra o plugin do detector de turno no SDK, e e isso que
# faz o `python -m agent.agent download-files` baixar o modelo na instalacao.
# Sem este import o modelo so seria procurado no primeiro turno de conversa -
# e falharia, porque a construcao dele exige contexto de job.
#
# Condicional para o modo "vad" nao pagar por um modelo que nao usa.
if settings.turn_detector.lower() == "multilingual":  # noqa: SIM108
    from livekit.plugins import turn_detector  # noqa: F401

logger = logging.getLogger("iara.pipeline")

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_pt_br.md"


def load_persona() -> str:
    """Carrega o arquivo de persona.

    Atencao ao papel deste arquivo agora que o n8n e' o cerebro: ele NAO
    decide mais o conteudo das respostas. Serve de referencia de tom para
    quem escreve os prompts do lado do n8n, e alimenta as poucas falas que
    ainda nascem aqui (saudacao e falha). Mudar este arquivo nao muda o que
    a IARA responde.
    """
    if not PROMPT_PATH.exists():
        raise RuntimeError(f"Prompt de persona nao encontrado: {PROMPT_PATH}")
    text = PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Prompt de persona vazio: {PROMPT_PATH}")
    return text


class IaraAgent(Agent):
    """Agente cujo raciocinio vive fora dele.

    `on_brain_reply` recebe a latencia do n8n e se houve enchimento de espera,
    para a instrumentacao. `on_end_session` e' chamado quando o fluxo sinaliza
    que a conversa acabou.
    """

    def __init__(
        self,
        brain: N8nBrain,
        *,
        on_brain_reply: Callable[[float, bool], None] | None = None,
        on_end_session: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(instructions=load_persona())
        self._brain = brain
        self._on_brain_reply = on_brain_reply
        self._on_end_session = on_end_session
        self._last_filler: str | None = None

    # -- enchimento de espera -------------------------------------------

    def _pick_filler(self, pool: list[str]) -> str:
        """Sorteia uma frase de espera sem repetir a anterior.

        Repetir a mesma frase dois turnos seguidos e' o que denuncia que ela
        e' automatica. Com quatro opcoes e essa regra, quase nunca acontece.
        """
        options = [f for f in pool if f != self._last_filler] or pool
        choice = random.choice(options)
        self._last_filler = choice
        return choice

    # -- substituicao do LLM ---------------------------------------------

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[Any],
        model_settings: ModelSettings,
    ) -> AsyncIterable[str | FlushSentinel]:
        user_text = _last_user_text(chat_ctx)
        if not user_text:
            logger.debug("turno sem texto do usuario, nada a enviar ao n8n")
            return

        task = asyncio.create_task(self._brain.ask(user_text))
        used_filler = False

        try:
            # Primeira janela: se o fluxo responder rapido, ninguem ouve
            # frase de espera nenhuma e a conversa soa normal.
            done, _ = await asyncio.wait({task}, timeout=settings.n8n_filler_after_s)

            if not done:
                used_filler = True
                yield self._pick_filler(settings.filler_phrases)
                # O sentinel obriga o TTS a fechar este trecho e comecar a
                # falar agora. Sem ele o texto ficaria no buffer esperando o
                # resto da geracao, que e' exatamente o que estamos evitando.
                yield FlushSentinel()

                # Segunda janela, para fluxo clinico longo. A primeira frase
                # e' curta; se a espera passar disso, uma segunda mais
                # explicita evita a sensacao de travamento.
                if settings.n8n_second_filler_after_s > 0:
                    done, _ = await asyncio.wait(
                        {task}, timeout=settings.n8n_second_filler_after_s
                    )
                    if not done:
                        yield self._pick_filler(settings.filler_phrases_long)
                        yield FlushSentinel()

            reply: BrainReply = await task

        except asyncio.CancelledError:
            # Barge-in: o usuario cortou. A requisicao ao n8n morre junto,
            # senao o fluxo continua rodando para uma resposta que ninguem
            # vai ouvir - e, num fluxo clinico com estado, avanca o passo
            # errado.
            logger.info("turno cancelado pelo usuario, abortando chamada ao n8n")
            raise

        except BrainError as exc:
            logger.error("n8n falhou: %s", exc)
            yield settings.brain_failure_text
            return

        finally:
            if not task.done():
                task.cancel()

        if self._on_brain_reply is not None:
            self._on_brain_reply(reply.latency_ms, used_filler)

        yield reply.text

        if reply.end_session and self._on_end_session is not None:
            self._on_end_session()


class N8nSentinelLLM(llm.LLM):
    """LLM de mentira que existe por um unico motivo, e ele e' importante.

    A resposta da IARA nasce no `llm_node` sobrescrito em IaraAgent, que
    chama o n8n. So' que o SDK, antes de chamar o llm_node, faz:

        elif self.llm is None:
            return  # skip response if no llm is set

    Ou seja: sem um `llm=` na AgentSession, o SDK descarta o turno do usuario
    em silencio - transcreve, fecha o turno, e nao responde nada. Nenhum erro,
    nenhum aviso. Foi assim que o M2 falhou na primeira vez: saudacao ok,
    transcricao ok, e depois nada.

    Esta classe satisfaz a verificacao. Se o `chat()` dela for chamado algum
    dia, e' porque o llm_node deixou de ser sobrescrito, e ai e' melhor
    quebrar alto do que responder errado.
    """

    @property
    def model(self) -> str:
        return "n8n-webhook"

    @property
    def provider(self) -> str:
        return "n8n"

    def chat(self, **_kwargs: Any) -> llm.LLMStream:
        raise RuntimeError(
            "N8nSentinelLLM.chat() foi chamado. O llm_node de IaraAgent deveria "
            "ter interceptado a geracao; confira se IaraAgent esta sendo usado."
        )


def _last_user_text(chat_ctx: llm.ChatContext) -> str:
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) != "message":
            continue
        if getattr(item, "role", None) != "user":
            continue
        text = getattr(item, "text_content", None)
        if text and text.strip():
            return text.strip()
    return ""


def _build_turn_detection() -> Any:
    """Escolhe o detector de fim de turno.

    inference    - modelo hospedado pela LiveKit, sem download local (padrao)
    multilingual - modelo local multilingue, roda no processo do agente
    vad          - so VAD, menor latencia e maior taxa de corte indevido
    """
    mode = (settings.turn_detector or "inference").lower()

    if mode == "vad":
        return "vad"

    if mode == "multilingual":
        from livekit.plugins.turn_detector.multilingual import MultilingualModel

        return MultilingualModel()

    from livekit.agents import inference

    return inference.TurnDetector()


def build_stt() -> deepgram.STT:
    kwargs: dict[str, Any] = {
        "model": settings.deepgram_model,
        "language": settings.stt_language,
        # O padrao do plugin e False. Ligado, a transcricao chega ao n8n
        # pontuada e com numeros e datas normalizados, em vez de um bloco
        # de palavras soltas.
        "smart_format": True,
    }

    # keyterm so existe no nova-3; em nova-2 o parametro equivalente e outro
    # e mandar este quebraria a conexao.
    if settings.stt_keyterms and settings.deepgram_model.startswith("nova-3"):
        kwargs["keyterm"] = list(settings.stt_keyterms)

    return deepgram.STT(**kwargs)


def build_tts() -> elevenlabs.TTS:
    settings.require("elevenlabs_voice_id")
    return elevenlabs.TTS(
        voice_id=settings.elevenlabs_voice_id,
        model=settings.elevenlabs_model,
        language=settings.tts_language,
    )


def build_session() -> AgentSession:
    """AgentSession com LLM sentinela, e barge-in tratado como requisito.

    Sobre os numeros de interrupcao: mode="vad" corta pelo sinal de voz, sem
    esperar a transcricao. E o caminho mais curto para ficar abaixo dos 300 ms
    exigidos. O preco e cortar em tosse e "aham", entao ligamos a deteccao de
    falsa interrupcao: se em 1,2 s nao vier fala de verdade, o avatar retoma
    de onde parou em vez de ficar mudo esperando o usuario.
    """
    session = AgentSession(
        stt=build_stt(),
        # Nao e' o cerebro: ver N8nSentinelLLM. Sem isto o SDK pula a resposta.
        llm=N8nSentinelLLM(),
        tts=build_tts(),
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(
            turn_detection=_build_turn_detection(),
            interruption={
                "enabled": True,
                "mode": "vad",
                "min_duration": 0.2,
                "min_words": 0,
                "false_interruption_timeout": 1.2,
                "resume_false_interruption": True,
                "discard_audio_if_uninterruptible": True,
            },
            endpointing={
                "min_delay": 0.3,
                "max_delay": 2.0,
            },
            user_turn_limit={
                "max_duration": 60.0,
            },
        ),
    )

    logger.info(
        "pipeline montado stt=deepgram/%s cerebro=n8n tts=elevenlabs/%s voz=%s",
        settings.deepgram_model,
        settings.elevenlabs_model,
        settings.elevenlabs_voice_id,
    )
    return session
