"""Token server.

Existe por um motivo unico e inegociavel: um APK e descompilavel. Nenhuma
chave de API pode viver dentro do app. O app so conhece a URL deste servico e
um segredo compartilhado, e recebe de volta um token de sala com escopo
minimo e prazo curto.

Rodar:
    uvicorn token_server.main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, status
from livekit import api
from pydantic import BaseModel, Field

from agent.avatar import create_avatar_engine
from agent.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iara.token")

app = FastAPI(title="IARA token server", version="1.0.0")

_SAFE_IDENTITY = re.compile(r"[^A-Za-z0-9_.:-]")


class TokenRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=128)


class TokenResponse(BaseModel):
    livekit_url: str
    token: str
    room: str
    expires_in_s: int


def require_shared_secret(x_api_key: str = Header(default="")) -> None:
    """Autenticacao de fase 1: chave estatica no header.

    Na fase 2 quem chama este endpoint passa a ser o n8n, apos identificar o
    usuario pelo WhatsApp, e esta funcao vira a verificacao daquele fluxo.
    Ate la, a chave estatica e o que impede um terceiro de queimar minutos de
    avatar por conta do cliente.
    """
    expected = settings.token_server_shared_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TOKEN_SERVER_SHARED_SECRET nao configurado no servidor.",
        )
    # comparacao de tamanho constante
    if not _constant_time_eq(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave invalida."
        )


def _constant_time_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@app.get("/health")
async def health() -> dict:
    """Readiness: config do LiveKit, do webhook do n8n e do motor de avatar.

    Checagem rasa de proposito: valida configuracao, nao importa plugin. Este
    processo so' emite tokens, e nao pode cair por causa de dependencia de
    avatar - ainda mais porque uma falha nativa mataria o processo inteiro,
    sem passar por except nenhum.
    """
    problems: list[str] = []

    for name in ("livekit_url", "livekit_api_key", "livekit_api_secret"):
        if not getattr(settings, name):
            problems.append(f"{name.upper()} ausente")

    if not settings.n8n_webhook_url:
        problems.append("N8N_WEBHOOK_URL ausente (o cerebro da IARA)")

    try:
        engine_health = await create_avatar_engine().health()
        engine_info = {
            "engine": engine_health.engine,
            "ok": engine_health.ok,
            "detail": engine_health.detail,
        }
        if not engine_health.ok:
            problems.append(f"avatar: {engine_health.detail}")
    except Exception as exc:  # configuracao invalida nao derruba o endpoint
        engine_info = {"engine": settings.avatar_engine, "ok": False, "detail": str(exc)}
        problems.append(f"avatar: {exc}")

    return {
        "ok": not problems,
        "avatar": engine_info,
        "cerebro": {"n8n": bool(settings.n8n_webhook_url)},
        "problemas": problems,
    }


async def dispatch_agent(room: str) -> None:
    """Pede ao LiveKit que coloque o agente da IARA nesta sala.

    O agente registra com `agent_name`, entao o LiveKit NAO o coloca sozinho
    em sala nenhuma - e' de proposito, para ele nao entrar em sala que nao e'
    dele. Quem decide e' este servico, no momento em que emite o token.

    Se falhar, a chamada e' recusada aqui mesmo. A alternativa seria devolver
    o token e o usuario cair numa sala vazia, olhando para o circulo girando
    sem entender por que ninguem aparece.
    """
    lkapi = api.LiveKitAPI(
        url=settings.livekit_url.replace("ws://", "http://").replace("wss://", "https://"),
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(room=room, agent_name=settings.agent_name)
        )
        logger.info("agente %s despachado para %s", settings.agent_name, room)
    except Exception as exc:
        logger.exception("falha ao despachar o agente para %s", room)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A IARA esta indisponivel no momento.",
        ) from exc
    finally:
        await lkapi.aclose()


@app.post(
    "/token",
    response_model=TokenResponse,
    dependencies=[Depends(require_shared_secret)],
)
async def create_token(req: TokenRequest) -> TokenResponse:
    settings.require("livekit_url", "livekit_api_key", "livekit_api_secret")

    room = f"session-{uuid.uuid4()}"
    identity = _SAFE_IDENTITY.sub("_", req.user_id)[:128] or "user"
    ttl_minutes = settings.token_ttl_minutes

    grants = api.VideoGrants(
        room_join=True,
        room=room,
        # O app fala e assiste. Nao publica video, nao administra a sala.
        can_publish=True,
        can_publish_data=True,
        can_subscribe=True,
        # Necessario para o app avisar o agente de que ja esta recebendo o
        # avatar (atributo app.avatar_ready). Sem isto o agente comeca a falar
        # antes de o app assinar as faixas e o comeco da frase se perde.
        can_update_own_metadata=True,
        room_admin=False,
        room_create=False,
    )

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(req.display_name or identity)
        .with_ttl(timedelta(minutes=ttl_minutes))
        .with_grants(grants)
        .to_jwt()
    )

    # O agente entra antes de o app conectar. Assim o avatar ja esta na sala
    # quando o usuario chega, em vez de o usuario esperar olhando o circulo.
    await dispatch_agent(room)

    logger.info("token emitido room=%s identity=%s ttl=%smin", room, identity, ttl_minutes)

    return TokenResponse(
        livekit_url=settings.livekit_url,
        token=token,
        room=room,
        expires_in_s=ttl_minutes * 60,
    )
