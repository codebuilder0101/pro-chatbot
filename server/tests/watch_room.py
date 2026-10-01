"""Observador de uma sala do LiveKit: conta video e mede a fala do avatar.

Serve para responder "o avatar apareceu e falou?" sem depender do app nem do
token server. Entra numa sala ja existente, assina tudo que o avatar publica e
imprime um perfil por segundo.

    python tests/watch_room.py NOME-DA-SALA [segundos]

Usar junto com tests/m1_avatar.py, que sobe o avatar na mesma sala:

    AVATAR_ENGINE=bithuman python tests/m1_avatar.py minha-sala &
    python tests/watch_room.py minha-sala 45

Limiar de voz: a faixa de audio do avatar fica em silencio digital, com pico
perto de 0, quando ele nao fala, e passa de 20000 quando fala. Por isso 900
separa bem as duas coisas. Conferido em 22/09/2026.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from livekit import api, rtc  # noqa: E402

from agent.config import settings  # noqa: E402

LIMIAR_VOZ = 900


async def main(sala: str, segundos: float) -> int:
    settings.require("livekit_url", "livekit_api_key", "livekit_api_secret")

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity("observador")
        .with_ttl(timedelta(minutes=30))
        .with_grants(
            api.VideoGrants(room_join=True, room=sala, can_subscribe=True)
        )
        .to_jwt()
    )

    room = rtc.Room()
    t0 = time.monotonic()
    video_frames = 0
    primeiro_frame: float | None = None
    dimensao = ""
    picos: dict[int, int] = {}
    quem: set[str] = set()
    tarefas: list[asyncio.Task] = []

    async def ler_video(track: rtc.Track) -> None:
        nonlocal video_frames, primeiro_frame, dimensao
        async for ev in rtc.VideoStream(track):
            video_frames += 1
            if primeiro_frame is None:
                primeiro_frame = time.monotonic() - t0
                dimensao = f"{ev.frame.width}x{ev.frame.height}"
                print(
                    f"  [{primeiro_frame:5.1f}s] PRIMEIRO FRAME de video {dimensao}",
                    flush=True,
                )

    async def ler_audio(track: rtc.Track) -> None:
        async for ev in rtc.AudioStream(track):
            s = int(time.monotonic() - t0)
            # ev.frame.data ja vem como int16; nao chamar .cast("h") nele.
            amostras = ev.frame.data
            pico = 0
            for i in range(0, len(amostras), 8):
                v = amostras[i]
                if v < 0:
                    v = -v
                if v > pico:
                    pico = v
            if pico > picos.get(s, 0):
                picos[s] = pico

    @room.on("track_subscribed")
    def _(track: rtc.Track, pub: rtc.TrackPublication, part: rtc.RemoteParticipant):
        quem.add(part.identity)
        marca = time.monotonic() - t0
        if track.kind == rtc.TrackKind.KIND_VIDEO:
            print(f"  [{marca:5.1f}s] assinou VIDEO de {part.identity}", flush=True)
            tarefas.append(asyncio.create_task(ler_video(track)))
        elif track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"  [{marca:5.1f}s] assinou AUDIO de {part.identity}", flush=True)
            tarefas.append(asyncio.create_task(ler_audio(track)))

    print(f"=== observando a sala {sala} por {segundos:.0f}s ===", flush=True)
    await room.connect(settings.livekit_url, token)
    print(f"  [  0.0s] conectado", flush=True)

    await asyncio.sleep(segundos)

    for t in tarefas:
        t.cancel()
    await room.disconnect()

    falando = sorted(s for s, p in picos.items() if p > LIMIAR_VOZ)
    print()
    print("=== resultado ===")
    print(f"  participantes vistos .......... {', '.join(sorted(quem)) or 'nenhum'}")
    print(f"  frames de video ............... {video_frames} {dimensao}")
    print(
        "  primeiro frame ................ "
        + (f"{primeiro_frame:.1f}s" if primeiro_frame is not None else "NUNCA")
    )
    print(f"  segundos com voz .............. {len(falando)} -> {falando}")
    if picos:
        print(f"  pico maximo de audio .......... {max(picos.values())}")
    print()
    ok = video_frames > 0 and bool(falando)
    print("RESULTADO:", "avatar apareceu e falou" if ok else "FALHOU")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    raise SystemExit(asyncio.run(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 45.0)))
