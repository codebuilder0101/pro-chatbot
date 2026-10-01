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

from .codes import CodigoInvalido, RegistroDeCodigos
from .db import Banco
from .users import ErroDeCadastro, Usuario, Usuarios

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iara.token")

app = FastAPI(title="IARA token server", version="1.2.0")

_SAFE_IDENTITY = re.compile(r"[^A-Za-z0-9_.:-]")

#: Registro de códigos de acesso. O arquivo é a fonte da verdade.
codigos = RegistroDeCodigos(settings.access_codes_path)

#: Banco de contas. Sem DSN configurado o serviço sobe sem cadastro, o que
#: mantém o modo "só código de acesso" funcionando.
banco = Banco(settings.database_url)
usuarios = Usuarios(banco, dias_de_sessao=settings.session_days)


@app.on_event("startup")
async def _ligar_banco() -> None:
    if not banco.configurado:
        logger.warning("DATABASE_URL ausente: cadastro de usuarios desligado")
        return
    try:
        await banco.conectar()
    except Exception:
        # Subir sem banco e' melhor do que nao subir: o /health denuncia, e
        # quem ja tem codigo de acesso continua conversando.
        logger.exception("falha ao conectar no banco; cadastro ficara indisponivel")


@app.on_event("shutdown")
async def _desligar_banco() -> None:
    await banco.fechar()


class TokenRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=128)
    # Digitado pela pessoa no app, nunca embutido no APK. Opcional no modelo
    # para que a ausencia vire 401 com mensagem clara, e nao 422 do pydantic.
    access_code: str = Field(default="", max_length=64)


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


def require_admin_token(x_admin_token: str = Header(default="")) -> None:
    """Protege a administracao de codigos.

    Estes endpoints nao sao publicados pelo nginx: so' respondem em
    127.0.0.1. O token e' a segunda tranca, para o caso de alguem publicar a
    porta por engano um dia.
    """
    esperado = settings.admin_token
    if not esperado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN nao configurado no servidor.",
        )
    if not _constant_time_eq(x_admin_token, esperado):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de admin invalido."
        )


#: Mensagem unica para qualquer recusa de codigo. De proposito: dizer "codigo
#: vencido" em vez de "codigo desconhecido" entrega ao atacante quais codigos
#: existem. O motivo real vai para o log do servidor.
_RECUSA = (
    "Codigo de acesso invalido ou sem saldo. "
    "Confira com quem te passou o codigo."
)


def _token_do_header(authorization: str) -> str:
    """Extrai o token de `Authorization: Bearer <token>`."""
    partes = (authorization or "").split(None, 1)
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1].strip()
    return ""


async def _usuario_autenticado(authorization: str) -> Usuario:
    """Exige sessao valida. So' e' chamada quando ha banco ligado."""
    usuario = await usuarios.usuario_da_sessao(_token_do_header(authorization))
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessao expirada. Entre de novo.",
        )
    return usuario


async def _autorizar(codigo: str, sala: str):
    """Valida o codigo e reserva o pior caso de minutos da sessao."""
    if not settings.access_codes_required:
        # Modo aberto, so' para desenvolvimento local. Em producao fica
        # ligado; o 06_agent_prod.sh recusa subir com isto desligado.
        from .codes import Autorizacao

        return Autorizacao(codigo="(livre)", empresa="(sem codigo)", minutos_reservados=0)

    try:
        return await codigos.autorizar(codigo, sala, settings.session_max_minutes)
    except CodigoInvalido as exc:
        logger.warning("codigo recusado sala=%s motivo=%s", sala, exc.motivo)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_RECUSA
        ) from exc
    except (OSError, ValueError) as exc:
        logger.exception("falha ao ler o registro de codigos")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servico de acesso indisponivel.",
        ) from exc


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

    # Banco ausente nao e' problema por si: o servico funciona so' com codigo
    # de acesso. Vira problema quando foi configurado e nao conectou.
    contas = {"configurado": banco.configurado, "ligado": banco.ligado}
    if banco.configurado and not banco.ligado:
        problems.append("banco de contas configurado mas sem conexao")

    return {
        "ok": not problems,
        "avatar": engine_info,
        "cerebro": {"n8n": bool(settings.n8n_webhook_url)},
        "contas": contas,
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
async def create_token(
    req: TokenRequest, authorization: str = Header(default="")
) -> TokenResponse:
    settings.require("livekit_url", "livekit_api_key", "livekit_api_secret")

    # Com banco ligado, quem manda e' a conta: a sessao diz quem e' a pessoa e
    # de qual empresa ela e'. O codigo no corpo passa a ser ignorado, para que
    # ninguem contorne a conta mandando um codigo solto.
    #
    # Sem banco, o servico continua funcionando so' com o codigo de acesso.
    # Isso mantem instalacoes antigas de pe e permite desenvolver sem Postgres.
    usuario: Usuario | None = None
    codigo_do_pedido = req.access_code
    if banco.ligado:
        usuario = await _usuario_autenticado(authorization)
        codigo_do_pedido = usuario.codigo_acesso or ""

    room = f"session-{uuid.uuid4()}"
    # Com conta, a identidade na sala e' o id do usuario, nao um UUID de
    # aparelho: assim a sala fica rastreavel ate a pessoa nos logs.
    bruto = f"u{usuario.id}" if usuario else req.user_id
    identity = _SAFE_IDENTITY.sub("_", bruto)[:128] or "user"
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

    # Reserva o pior caso de minutos ANTES de emitir qualquer coisa. Se o
    # codigo nao servir, nada e' despachado e nenhum minuto pago e' aberto.
    autorizacao = await _autorizar(codigo_do_pedido, room)

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name((usuario.nome if usuario else "") or req.display_name or identity)
        .with_ttl(timedelta(minutes=ttl_minutes))
        .with_grants(grants)
        .to_jwt()
    )

    # O agente entra antes de o app conectar. Assim o avatar ja esta na sala
    # quando o usuario chega, em vez de o usuario esperar olhando o circulo.
    try:
        await dispatch_agent(room)
    except Exception:
        # Despacho falhou: devolve a reserva, senao o minuto fica preso num
        # codigo por causa de um erro que nao foi do usuario.
        await codigos.encerrar(room, 0)
        raise

    logger.info(
        "token emitido room=%s identity=%s ttl=%smin codigo=%s empresa=%r",
        room, identity, ttl_minutes, autorizacao.codigo, autorizacao.empresa,
    )

    return TokenResponse(
        livekit_url=settings.livekit_url,
        token=token,
        room=room,
        expires_in_s=ttl_minutes * 60,
    )


# ============================================================
# Fim de sessao: o agente avisa quanto tempo a conversa durou
# ============================================================


class FimDeSessao(BaseModel):
    room: str = Field(min_length=1, max_length=200)
    minutos: float = Field(ge=0, le=24 * 60)


@app.post("/session-ended", dependencies=[Depends(require_shared_secret)])
async def session_ended(req: FimDeSessao) -> dict:
    """Acerta a reserva de minutos com a duracao real.

    Chamado pelo agente no shutdown, em 127.0.0.1. Idempotente: a segunda
    chamada para a mesma sala nao cobra de novo.

    Se esta chamada nunca chegar, porque o agente morreu, a reserva do pior
    caso continua debitada. E' o lado certo para errar.
    """
    try:
        resultado = await codigos.encerrar(req.room, req.minutos)
    except (OSError, ValueError):
        logger.exception("falha ao acertar a sessao %s", req.room)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="indisponivel"
        ) from None
    return {"ok": True, "acerto": resultado}


# ============================================================
# Administracao dos codigos (apenas 127.0.0.1; use deploy/codes.py)
# ============================================================


class NovoCodigo(BaseModel):
    empresa: str = Field(min_length=1, max_length=200)
    codigo: str | None = Field(default=None, max_length=64)
    validade: str | None = Field(default=None, max_length=10)
    teto_minutos: int | None = Field(default=None, ge=1, le=1_000_000)


class AlteraCodigo(BaseModel):
    empresa: str | None = Field(default=None, max_length=200)
    ativo: bool | None = None
    validade: str | None = Field(default=None, max_length=10)
    teto_minutos: int | None = Field(default=None, ge=1, le=1_000_000)


@app.get("/admin/codes", dependencies=[Depends(require_admin_token)])
async def admin_listar() -> dict:
    return {"codigos": await codigos.listar()}


@app.post("/admin/codes", dependencies=[Depends(require_admin_token)])
async def admin_criar(req: NovoCodigo) -> dict:
    try:
        return await codigos.criar(
            req.empresa,
            codigo=req.codigo,
            validade=req.validade,
            teto_minutos=req.teto_minutos,
        )
    except CodigoInvalido as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.motivo) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="validade deve ser AAAA-MM-DD",
        ) from exc


@app.patch("/admin/codes/{codigo}", dependencies=[Depends(require_admin_token)])
async def admin_alterar(codigo: str, req: AlteraCodigo) -> dict:
    try:
        return await codigos.alterar(codigo, **req.model_dump())
    except CodigoInvalido as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.motivo) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="validade deve ser AAAA-MM-DD",
        ) from exc


@app.delete("/admin/codes/{codigo}", dependencies=[Depends(require_admin_token)])
async def admin_remover(codigo: str) -> dict:
    try:
        await codigos.remover(codigo)
    except CodigoInvalido as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.motivo) from exc
    return {"ok": True}


# ============================================================
# Contas: cadastro e entrada
# ============================================================


class CadastroRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=1, max_length=200)
    nome: str = Field(default="", max_length=120)
    # Diz de qual empresa a pessoa e'. Exigido: sem isto qualquer um criaria
    # conta e voltariamos ao problema que o codigo de acesso veio resolver.
    access_code: str = Field(default="", max_length=64)


class EntrarRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    senha: str = Field(min_length=1, max_length=200)


class SessaoResponse(BaseModel):
    session_token: str
    email: str
    nome: str
    expires_at: str


def _exigir_banco() -> None:
    if not banco.ligado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cadastro indisponivel no momento.",
        )


async def _conferir_codigo_do_cadastro(codigo: str) -> str | None:
    """O codigo so' e' validado, nunca consumido: cadastrar nao gasta minuto."""
    if not settings.access_codes_required:
        return None
    try:
        return await codigos.validar(codigo)
    except CodigoInvalido as exc:
        logger.warning("cadastro recusado motivo=%s", exc.motivo)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_RECUSA) from exc


@app.post("/auth/register", response_model=SessaoResponse, dependencies=[Depends(require_shared_secret)])
async def registrar(req: CadastroRequest) -> SessaoResponse:
    _exigir_banco()
    codigo = await _conferir_codigo_do_cadastro(req.access_code)
    try:
        await usuarios.cadastrar(
            email=req.email, senha=req.senha, nome=req.nome, codigo_acesso=codigo
        )
        # Entra direto apos cadastrar: pedir para digitar a senha de novo na
        # sequencia nao protege nada e so' irrita.
        sessao = await usuarios.entrar(email=req.email, senha=req.senha)
    except ErroDeCadastro as exc:
        raise HTTPException(status_code=exc.status, detail=exc.mensagem) from exc

    logger.info("cadastro concluido email=%s empresa=%s", sessao.usuario.email, codigo)
    return SessaoResponse(
        session_token=sessao.token,
        email=sessao.usuario.email,
        nome=sessao.usuario.nome,
        expires_at=sessao.expira_em.isoformat(timespec="seconds"),
    )


@app.post("/auth/login", response_model=SessaoResponse, dependencies=[Depends(require_shared_secret)])
async def entrar(req: EntrarRequest) -> SessaoResponse:
    _exigir_banco()
    try:
        sessao = await usuarios.entrar(email=req.email, senha=req.senha)
    except ErroDeCadastro as exc:
        raise HTTPException(status_code=exc.status, detail=exc.mensagem) from exc

    logger.info("entrada email=%s", sessao.usuario.email)
    return SessaoResponse(
        session_token=sessao.token,
        email=sessao.usuario.email,
        nome=sessao.usuario.nome,
        expires_at=sessao.expira_em.isoformat(timespec="seconds"),
    )


@app.post("/auth/logout", dependencies=[Depends(require_shared_secret)])
async def sair(authorization: str = Header(default="")) -> dict:
    if banco.ligado:
        await usuarios.sair(_token_do_header(authorization))
    return {"ok": True}
