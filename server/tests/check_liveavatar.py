"""Diagnostico do HeyGen LiveAvatar (AVATAR_ENGINE=heygen).

O plugin `livekit-plugins-liveavatar` abre uma sessao em modo LITE: o worker
do LiveAvatar entra na NOSSA sala LiveKit como participante e publica o video
com a boca casada ao audio que o agente manda por WebSocket. Para isso ele
precisa de tres coisas, e este script confere as tres sem gastar credito:

  1. chave valida (HEYGEN_API_KEY -> LIVEAVATAR_API_KEY)
  2. avatar existente, ACTIVE e "usable" (HEYGEN_AVATAR_ID)
  3. LIVEKIT_URL alcancavel pela internet - o worker roda na nuvem deles.
     `ws://10.0.2.2:7880` (emulador) ou `localhost` nunca vao funcionar:
     a sessao e' criada, o /start responde 200, e o video nunca chega.

Com `--session` abre uma sessao LITE de verdade numa sala descartavel, espera
o worker avisar `connected` e encerra em seguida. Isso CONSOME credito do
plano (o sandbox gratuito so' aceita avatares publicos do LiveAvatar, nao os
da conta). Use quando o /health esta verde e mesmo assim nao aparece video.

    python tests/check_liveavatar.py
    python tests/check_liveavatar.py --session

Le o .env/.env.local como o agente. Sem --session nao cria nada.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env.local")
load_dotenv(".env")

API = "https://api.liveavatar.com/v1"
# O Cloudflare na frente da API barra o user-agent padrao do urllib (erro 1010).
_UA = "iara-check-liveavatar/1.0"
_PRIVADOS = ("localhost", "127.", "10.", "192.168.", "0.0.0.0")


def _key() -> str:
    key = os.environ.get("HEYGEN_API_KEY") or os.environ.get("LIVEAVATAR_API_KEY")
    if not key:
        sys.exit("HEYGEN_API_KEY ausente no ambiente/.env")
    return key.strip()


def _get(path: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        API + path,
        headers={"X-API-KEY": _key(), "accept": "application/json", "User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"raw": body}


def _ok(msg: str) -> None:
    print(f"  ok      {msg}")


def _bad(msg: str) -> None:
    print(f"  ERRO    {msg}")


def check_key() -> bool:
    status, data = _get("/avatars?limit=50")
    if status == 401 or status == 403:
        _bad(f"chave recusada pela API ({status})")
        return False
    if status != 200:
        _bad(f"listagem de avatares falhou: {status} {data}")
        return False
    results = data.get("data", {}).get("results", [])
    _ok(f"chave aceita; {len(results)} avatar(es) na conta")
    for av in results:
        print(
            f"          - {av['id']}  {av['name']!r}  {av['type']}  "
            f"{av['status']}/{av.get('availability', 'n/d')}"
        )
    return True


def check_avatar() -> bool:
    avatar_id = (
        os.environ.get("HEYGEN_AVATAR_ID") or os.environ.get("LIVEAVATAR_AVATAR_ID") or ""
    ).strip()
    if not avatar_id:
        _bad("HEYGEN_AVATAR_ID ausente")
        return False
    status, data = _get(f"/avatars/{avatar_id}")
    if status == 404:
        _bad(f"avatar {avatar_id} nao existe nesta conta")
        return False
    if status != 200:
        _bad(f"consulta do avatar falhou: {status} {data}")
        return False
    av = data["data"]
    problems = []
    if av.get("status") != "ACTIVE":
        problems.append(f"status={av.get('status')}")
    # A API parou de mandar `availability` em 26/09/2026. Ausente nao e' erro:
    # so' reclama quando o campo existe e diz que o avatar nao serve.
    if "availability" in av and av["availability"] != "usable":
        problems.append(f"availability={av['availability']}")
    if av.get("is_expired"):
        problems.append("expirado")
    if problems:
        _bad(f"avatar {av['name']!r}: {', '.join(problems)}")
        return False
    _ok(f"avatar {av['name']!r} ({av['type']}) ativo e utilizavel")
    # error_message antiga fica gravada mesmo depois de o avatar ficar pronto;
    # so' importa se availability nao for usable.
    return True


def check_livekit() -> bool:
    url = os.environ.get("LIVEKIT_URL", "").strip()
    if not url:
        _bad("LIVEKIT_URL ausente")
        return False
    host = urlparse(url).hostname or ""
    if url.startswith("ws://") or host.startswith(_PRIVADOS) or host == "":
        _bad(
            f"LIVEKIT_URL={url} nao e' alcancavel pelo worker do LiveAvatar. "
            "Precisa ser wss:// publico (LiveKit Cloud ou o dominio do VPS)."
        )
        return False
    if not (os.environ.get("LIVEKIT_API_KEY") and os.environ.get("LIVEKIT_API_SECRET")):
        _bad("LIVEKIT_API_KEY / LIVEKIT_API_SECRET ausentes")
        return False
    _ok(f"LIVEKIT_URL={url}")
    return True


async def _stop(http, base: str, sid: str, auth: dict) -> None:
    async with http.post(
        base + "/stop", json={"session_id": sid, "reason": "USER_DISCONNECTED"}, headers=auth
    ) as r:
        print(f"          stop -> {r.status}")


async def open_session() -> bool:
    """Sessao LITE real, curta, numa sala descartavel. Gasta credito."""
    import aiohttp
    from livekit import api

    avatar_id = os.environ.get("HEYGEN_AVATAR_ID") or os.environ["LIVEAVATAR_AVATAR_ID"]
    room = f"check-liveavatar-{uuid.uuid4().hex[:8]}"
    token = (
        api.AccessToken(
            api_key=os.environ["LIVEKIT_API_KEY"],
            api_secret=os.environ["LIVEKIT_API_SECRET"],
        )
        .with_kind("agent")
        .with_identity("liveavatar-avatar-agent")
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )
    payload = {
        "mode": "LITE",
        "avatar_id": avatar_id,
        "is_sandbox": False,
        "video_quality": os.environ.get("HEYGEN_VIDEO_QUALITY", "high"),
        "livekit_config": {
            "livekit_room": room,
            "livekit_url": os.environ["LIVEKIT_URL"],
            "livekit_client_token": token,
        },
    }
    base = API + "/sessions"
    async with aiohttp.ClientSession() as http:
        async with http.post(base + "/token", json=payload, headers={"X-API-KEY": _key()}) as r:
            body = await r.json()
            if not r.ok:
                _bad(f"/sessions/token {r.status}: {body}")
                return False
        sid = body["data"]["session_id"]
        auth = {"Authorization": f"Bearer {body['data']['session_token']}"}
        print(f"          sessao {sid} sala {room}")

        async with http.post(base + "/start", json={"session_id": sid}, headers=auth) as r:
            body = await r.json()
            if not r.ok:  # o /start responde 201
                _bad(f"/sessions/start {r.status}: {body}")
                await _stop(http, base, sid, auth)
                return False
        ws_url = body["data"]["ws_url"]

        connected = False
        try:
            async with http.ws_connect(ws_url) as ws:
                for _ in range(60):
                    msg = await asyncio.wait_for(ws.receive(), timeout=30)
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        _bad(f"websocket fechou antes de conectar ({msg.type})")
                        break
                    ev = json.loads(msg.data)
                    print(f"          evento {ev.get('type')} {ev.get('state', '')}")
                    if ev.get("type") == "session.state_updated" and ev.get("state") == "connected":
                        connected = True
                        break
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            _bad(f"websocket: {exc!r}")
        finally:
            await _stop(http, base, sid, auth)

    if connected:
        _ok("worker do LiveAvatar entrou na sala e ficou connected")
    else:
        _bad(
            "worker nao chegou a 'connected'. Se chave e avatar estao ok, "
            "quase sempre e' o LIVEKIT_URL inalcancavel ou a chave do LiveKit errada."
        )
    return connected


def main() -> int:
    print("LiveAvatar (AVATAR_ENGINE=heygen)")
    results = [check_key(), check_avatar(), check_livekit()]
    if "--session" in sys.argv[1:]:
        if not all(results):
            _bad("corrija os itens acima antes de abrir uma sessao paga")
            return 1
        results.append(asyncio.run(open_session()))
    print()
    if all(results):
        print("tudo certo")
        return 0
    print("ha problemas acima")
    return 1


if __name__ == "__main__":
    sys.exit(main())
