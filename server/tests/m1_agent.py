"""M1 - worker minimo: o avatar entra na sala e fala uma frase fixa.

Usa **so** ElevenLabs e o motor de avatar. Sem Deepgram, sem LLM, sem n8n -
roda antes dessas chaves existirem, e e' o menor caminho para ver a IARA de pe.

    python tests/m1_agent.py dev

Diferencas para o agente de producao (agent/agent.py), todas de proposito:

  * sem `agent_name`, entao o LiveKit despacha automaticamente para qualquer
    sala nova. Em producao o despacho e' explicito, para o agente nao entrar
    em sala que nao e' dele.
  * AgentSession sem `stt` e sem `llm`: neste marco a IARA nao precisa ouvir
    nem pensar, so' falar.

Por que e' um worker e nao um script: o plugin do bitHuman chama
`get_job_context()` para descobrir a URL e o token da sala que deve entregar a
nuvem deles. Fora de um job isso levanta RuntimeError.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from livekit import agents  # noqa: E402
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, room_io  # noqa: E402

from agent.avatar import create_avatar_engine  # noqa: E402
from agent.agent import wait_for_app_ready  # noqa: E402
from agent.config import settings  # noqa: E402
from agent.pipeline import build_tts  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("iara.m1")

FRASE = (
    "Oi! Eu sou a IARA. Se voce esta me vendo falar, o avatar, a voz e a "
    "sincronia da boca estao funcionando."
)

server = AgentServer(
    host=settings.agent_http_host,
    port=settings.agent_http_port,
)


@server.rtc_session()
async def m1(ctx: JobContext) -> None:
    room_name = getattr(ctx.room, "name", "?")
    engine = create_avatar_engine()
    logger.info("M1 sala=%s motor=%s", room_name, engine.name)

    session = AgentSession(tts=build_tts())


    # O avatar precisa entrar antes do session.start(): e' ele quem assume a
    # saida de audio. Invertendo, o agente publica a propria voz e o usuario
    # ouve o audio duas vezes, fora de sincronia.
    await engine.start(session, room=ctx.room)
    logger.info("avatar publicado na sala")

    async def teardown() -> None:
        await engine.aclose()

    ctx.add_shutdown_callback(teardown)

    await session.start(
        room=ctx.room,
        agent=Agent(instructions="Voce e a IARA."),
        room_options=room_io.RoomOptions(
            audio_output=not engine.publishes_room_audio,
        ),
    )

    # Espera o app estar recebendo o avatar antes de falar, senao o comeco
    # da frase se perde.
    await wait_for_app_ready(ctx.room)

    handle = session.say(FRASE)
    await handle.wait_for_playout()
    logger.info("terminou de falar a frase do M1")


if __name__ == "__main__":
    agents.cli.run_app(server)
