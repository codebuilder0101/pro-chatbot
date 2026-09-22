"""Perfil de energia do audio do avatar, segundo a segundo.

Serve para saber se a faixa de audio do avatar carrega ruido continuo (o que
faria qualquer deteccao por energia mentir) ou so' os trechos de fala.
"""
import asyncio, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import aiohttp
from livekit import rtc
from agent.config import settings

async def main():
    base = "https://" + os.environ["TOKEN_SERVER_DOMAIN"].strip()
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{base}/token", json={"user_id": "perfil-audio"},
                             headers={"x-api-key": settings.token_server_shared_secret}) as r:
            creds = await r.json()
    room = rtc.Room()
    t0 = time.monotonic()
    picos = {}

    @room.on("track_subscribed")
    def _(track, pub, part):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"  audio de {part.identity} em {time.monotonic()-t0:.1f}s", flush=True)
            asyncio.create_task(ler(track))

    async def ler(track):
        async for ev in rtc.AudioStream(track):
            s = int(time.monotonic() - t0)
            a = ev.frame.data
            p = 0
            for i in range(0, len(a), 8):
                v = a[i]
                if v < 0: v = -v
                if v > p: p = v
            if p > picos.get(s, 0):
                picos[s] = p

    await room.connect(creds["livekit_url"], creds["token"])
    src = rtc.AudioSource(24000, 1)
    tr = rtc.LocalAudioTrack.create_audio_track("mic", src)
    await room.local_participant.publish_track(tr, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    await room.local_participant.set_attributes({"app.avatar_ready": "1"})
    print("  conectado; medindo 40s (so' a saudacao deve soar)", flush=True)
    await asyncio.sleep(40)
    await room.disconnect()
    print("\n  segundo: pico (0-32768)   [barra = fala]")
    for s in sorted(picos):
        p = picos[s]
        print(f"   {s:3d}s: {p:6d}  {'#' * min(40, p // 400)}")
    altos = [s for s, p in picos.items() if p > 900]
    print(f"\n  segundos acima do limiar 900: {len(altos)} de {len(picos)} -> {sorted(altos)}")

asyncio.run(main())
