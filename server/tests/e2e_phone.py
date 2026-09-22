"""Teste ponta a ponta: um "celular virtual" conversando com a IARA.

Faz exatamente o que o app Android faz, e mede o que o usuario veria:

  1. POST /token no token server publico (HTTPS, header x-api-key)
  2. entra na sala do LiveKit com o token recebido
  3. avisa `app.avatar_ready=1`, o mesmo handshake do app
  4. assina a faixa de VIDEO do avatar e conta os frames que chegam
  5. fala frases em portugues no microfone (audio sintetizado pelo
     ElevenLabs e publicado como faixa de microfone)
  6. escuta a resposta: mede quando o avatar volta a publicar audio

O que isso prova, e nenhum teste anterior provava: Deepgram entendeu a fala,
o n8n respondeu, o ElevenLabs falou e o LiveAvatar animou - tudo junto, pela
mesma porta que o APK vai usar.

    python tests/e2e_phone.py                     # roteiro padrao
    python tests/e2e_phone.py "uma frase sua"     # fala o que voce quiser

Custa creditos de verdade (LiveAvatar por minuto, ElevenLabs por caractere).
Roda no VPS, onde o .env de producao esta.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp  # noqa: E402
from livekit import rtc  # noqa: E402

from agent.config import settings  # noqa: E402

FRASES_PADRAO = [
    "Oi, bom dia! Tudo bem?",
    "Quero entender melhor a NR-1.",
]

SAMPLE_RATE = 24000
ELEVEN_TTS = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=pcm_24000"


def _log(msg: str) -> None:
    print(f"  {time.strftime('%H:%M:%S')}  {msg}", flush=True)


async def pedir_token(session: aiohttp.ClientSession, base: str, secret: str) -> dict:
    async with session.post(
        f"{base}/token",
        json={"user_id": "teste-e2e", "display_name": "Teste E2E"},
        headers={"x-api-key": secret},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as r:
        body = await r.text()
        if r.status != 200:
            raise RuntimeError(f"/token devolveu {r.status}: {body[:300]}")
        return json.loads(body)


async def sintetizar(session: aiohttp.ClientSession, texto: str) -> bytes:
    """Gera PCM 24 kHz mono do que o 'usuario' vai falar."""
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ["ELEVEN_API_KEY"]
    url = ELEVEN_TTS.format(voice=settings.elevenlabs_voice_id)
    payload = {
        "text": texto,
        "model_id": settings.elevenlabs_model,
        "language_code": settings.tts_language or None,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    async with session.post(
        url, json=payload, headers={"xi-api-key": key},
        timeout=aiohttp.ClientTimeout(total=60),
    ) as r:
        if r.status != 200:
            raise RuntimeError(f"TTS falhou {r.status}: {(await r.text())[:200]}")
        return await r.read()


class Monitor:
    """Conta o que chega do avatar: frames de video e trechos de audio."""

    def __init__(self) -> None:
        self.video_frames = 0
        self.primeiro_frame_em: float | None = None
        self.audio_frames = 0
        self.audio_janelas: list[float] = []  # instantes com audio audivel
        self.identidade: str | None = None
        self._t0 = time.monotonic()
        self._tasks: list[asyncio.Task] = []

    def anexar(self, room: rtc.Room) -> None:
        @room.on("track_subscribed")
        def _(track: rtc.Track, pub: rtc.TrackPublication, part: rtc.RemoteParticipant):
            self.identidade = part.identity
            if track.kind == rtc.TrackKind.KIND_VIDEO:
                _log(f"assinou VIDEO de {part.identity}")
                self._tasks.append(asyncio.create_task(self._ler_video(track)))
            elif track.kind == rtc.TrackKind.KIND_AUDIO:
                _log(f"assinou AUDIO de {part.identity}")
                self._tasks.append(asyncio.create_task(self._ler_audio(track)))

    async def _ler_video(self, track: rtc.Track) -> None:
        stream = rtc.VideoStream(track)
        async for ev in stream:
            self.video_frames += 1
            if self.primeiro_frame_em is None:
                self.primeiro_frame_em = time.monotonic() - self._t0
                f = ev.frame
                _log(
                    f"PRIMEIRO FRAME de video em {self.primeiro_frame_em:.1f}s "
                    f"({f.width}x{f.height})"
                )

    async def _ler_audio(self, track: rtc.Track) -> None:
        stream = rtc.AudioStream(track)
        async for ev in stream:
            self.audio_frames += 1
            # ev.frame.data ja vem como memoryview de int16 (format "h").
            # Chamar .cast("h") nele levanta TypeError e mata esta task em
            # silencio - foi o que escondeu o audio no primeiro teste.
            amostras = ev.frame.data
            pico = 0
            for i in range(0, len(amostras), 8):  # 1 em cada 8 basta
                v = amostras[i]
                if v < 0:
                    v = -v
                if v > pico:
                    pico = v
            if pico > 900:
                self.audio_janelas.append(time.monotonic() - self._t0)

    async def aclose(self) -> None:
        for t in self._tasks:
            t.cancel()

    def agora(self) -> float:
        return time.monotonic() - self._t0

    def falou_entre(self, inicio: float, fim: float) -> bool:
        return any(inicio <= t <= fim for t in self.audio_janelas)

    async def esperar_fala(self, desde: float, timeout: float) -> float | None:
        """Espera o avatar comecar a falar. Devolve quando comecou."""
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            for t in self.audio_janelas:
                if t >= desde:
                    return t
            await asyncio.sleep(0.2)
        return None

    async def esperar_resposta_completa(
        self, desde: float, quieto_por: float = 35.0, timeout: float = 180.0
    ) -> tuple[float | None, bool]:
        """Espera a resposta inteira: comecar a falar e depois ficar quieta.

        `quieto_por` precisa ser MAIOR que N8N_TIMEOUT_S (30 s), senao a
        pausa entre a frase de espera ("deixa eu ver") e a resposta de verdade
        passa por fim de turno, a proxima fala do usuario vira barge-in e o
        turno e' cancelado - foi o que aconteceu na primeira versao deste teste.
        """
        comecou = await self.esperar_fala(desde, timeout=45)
        if comecou is None:
            return None, False
        terminou = await self.esperar_silencio(quieto_por=quieto_por, timeout=timeout)
        return comecou, terminou

    async def esperar_silencio(self, quieto_por: float = 2.0, timeout: float = 90.0) -> bool:
        """Espera o avatar parar de falar - senao a proxima frase vira barge-in."""
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            ultimo = self.audio_janelas[-1] if self.audio_janelas else -1e9
            if self.agora() - ultimo >= quieto_por:
                return True
            await asyncio.sleep(0.3)
        return False


async def publicar_fala(source: rtc.AudioSource, pcm: bytes) -> float:
    """Empurra o PCM no microfone virtual, em tempo real."""
    chunk = SAMPLE_RATE // 50 * 2  # 20 ms
    t0 = time.monotonic()
    for i in range(0, len(pcm) - chunk, chunk):
        frame = rtc.AudioFrame(
            data=pcm[i : i + chunk],
            sample_rate=SAMPLE_RATE,
            num_channels=1,
            samples_per_channel=chunk // 2,
        )
        await source.capture_frame(frame)
    return time.monotonic() - t0


async def main() -> int:
    frases = sys.argv[1:] or FRASES_PADRAO
    # TOKEN_SERVER_DOMAIN nao esta no Settings (so' o deploy usa); le do ambiente.
    dominio = os.environ.get("TOKEN_SERVER_DOMAIN", "").strip()
    base = os.environ.get("E2E_BASE") or (f"https://{dominio}" if dominio else "")
    secret = settings.token_server_shared_secret
    if not base.startswith("https://") or not secret:
        print("defina TOKEN_SERVER_DOMAIN e TOKEN_SERVER_SHARED_SECRET no .env")
        return 1

    print(f"=== celular virtual -> {base} ===")
    http = aiohttp.ClientSession()
    room = rtc.Room()
    mon = Monitor()
    ok = True
    try:
        creds = await pedir_token(http, base, secret)
        _log(f"token ok: sala={creds['room']} ttl={creds['expires_in_s']}s")

        mon.anexar(room)
        await room.connect(creds["livekit_url"], creds["token"])
        _log(f"entrou na sala como {room.local_participant.identity}")

        # microfone virtual, publicado como o app publica
        source = rtc.AudioSource(SAMPLE_RATE, 1)
        track = rtc.LocalAudioTrack.create_audio_track("microfone", source)
        await room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        _log("microfone publicado")

        # o handshake que impede a saudacao de sair cortada
        await room.local_participant.set_attributes({"app.avatar_ready": "1"})
        _log("avisou app.avatar_ready=1")

        # saudacao: o agente fala assim que o app se anuncia
        comeco = mon.agora()
        inicio_fala = await mon.esperar_fala(comeco, timeout=30)
        if inicio_fala is not None:
            _log(f"OK: avatar falou a saudacao ({inicio_fala - comeco:.1f}s depois do ready)")
        else:
            _log("FALHOU: nenhuma saudacao audivel em 30s")
            ok = False

        # deixar a saudacao terminar inteira antes da primeira pergunta
        await mon.esperar_silencio(quieto_por=12.0, timeout=120)

        for n, frase in enumerate(frases, 1):
            _log(f'usuario diz: "{frase}"')
            pcm = await sintetizar(http, frase)
            await publicar_fala(source, pcm)
            fim_fala = mon.agora()
            comecou, terminou = await mon.esperar_resposta_completa(fim_fala + 0.5)
            if comecou is None:
                _log(f"FALHOU: nenhuma resposta audivel para a frase {n}")
                ok = False
            else:
                marca = "completa" if terminou else "ainda falando no fim do timeout"
                _log(f"OK: a IARA comecou a responder em {comecou - fim_fala:.1f}s ({marca})")

        # nao desconectar em cima da ultima palavra
        await asyncio.sleep(2)

        print()
        print("=== resultado ===")
        print(f"  frames de video recebidos ..... {mon.video_frames}")
        print(
            "  1o frame ...................... "
            + (f"{mon.primeiro_frame_em:.1f}s" if mon.primeiro_frame_em else "NUNCA")
        )
        print(f"  quadros de audio do avatar .... {mon.audio_frames}")
        print(f"  trechos com voz ............... {len(mon.audio_janelas)}")
        print(f"  participante do avatar ........ {mon.identidade}")
        if mon.video_frames == 0:
            ok = False
        print()
        print("RESULTADO:", "TUDO OK" if ok else "HOUVE FALHA")
        return 0 if ok else 1
    finally:
        await mon.aclose()
        await room.disconnect()
        await http.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
