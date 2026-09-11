"""M1 - o avatar aparece e fala uma frase fixa, com a boca sincronizada.

E' o primeiro marco da especificacao, e o menor caminho para ver a IARA de pe:
usa **so** ElevenLabs e o motor de avatar. Sem Deepgram, sem LLM, sem n8n -
por isso roda antes dessas chaves existirem.

    python tests/m1_avatar.py [nome-da-sala]

O que ele faz:
  1. entra numa sala do LiveKit como participante
  2. liga o motor de avatar (bitHuman ou HeyGen, conforme AVATAR_ENGINE)
  3. manda a IARA falar uma frase

Depois e' so' abrir o app apontando para a mesma sala, ou olhar os
participantes pela API do LiveKit.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from livekit import api, rtc  # noqa: E402
from livekit.agents import AgentSession, room_io  # noqa: E402

from agent.avatar import create_avatar_engine  # noqa: E402
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


async def main(room_name: str) -> int:
    settings.require("livekit_url", "livekit_api_key", "livekit_api_secret")

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity("iara-m1")
        .with_name("IARA")
        .with_ttl(timedelta(minutes=15))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )

    room = rtc.Room()
    logger.info("conectando em %s sala=%s", settings.livekit_url, room_name)
    await room.connect(settings.livekit_url, token)
    logger.info("conectado")

    # Sessao so' com TTS: sem stt e sem llm, porque neste marco a IARA nao
    # precisa ouvir nem pensar - so' falar.
    session = AgentSession(tts=build_tts())

    engine = create_avatar_engine()
    logger.info("ligando avatar: %s", engine.name)
    await engine.start(session, room=room)
    logger.info("avatar na sala")

    await session.start(
        room=room,
        room_options=room_io.RoomOptions(
            audio_output=not engine.publishes_room_audio,
        ),
    )

    handle = session.say(FRASE)
    logger.info("falando...")
    await handle.wait_for_playout()
    logger.info("terminou de falar")

    # Fica de pe um tempo para dar tempo de olhar pelo app.
    logger.info("mantendo a sessao por 3 minutos; Ctrl+C encerra antes")
    try:
        await asyncio.sleep(180)
    except asyncio.CancelledError:
        pass
    finally:
        await engine.aclose()
        await room.disconnect()
        logger.info("encerrado")

    return 0


if __name__ == "__main__":
    sala = sys.argv[1] if len(sys.argv) > 1 else "m1-teste"
    try:
        raise SystemExit(asyncio.run(main(sala)))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
