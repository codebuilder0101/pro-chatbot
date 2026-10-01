"""Entrypoint do agente LiveKit da IARA.

Executar:
    python -m agent.agent dev        # desenvolvimento, recarrega ao salvar
    python -m agent.agent start      # producao

O agente entra na mesma sala que o app, escuta o microfone do usuario, manda
o texto ao fluxo do n8n, e entrega a resposta ao TTS e ao motor de avatar.
Quem publica video e audio na sala e o motor de avatar, nao o agente.

O raciocinio nao mora aqui. O agente e' encanamento: ouvido, boca e rosto.
O cerebro clinico e' o workflow do n8n.

API conferida em 2026-09-04 contra livekit-agents 1.7.1: AgentServer +
@server.rtc_session + session.start(room_options=room_io.RoomOptions(...)),
`llm` opcional na AgentSession e `llm_node` aceitando `str`/`FlushSentinel`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from livekit import agents
from livekit.agents import AgentServer, JobContext, room_io

from .avatar import create_avatar_engine
from .config import settings
from .metrics import AvatarVideoProbe, TurnMetricsRecorder, safe_on
from .n8n import BrainError, N8nBrain
from .pipeline import IaraAgent, build_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("iara.agent")

server = AgentServer(
    host=settings.agent_http_host,
    port=settings.agent_http_port,
)


class SessionLimits:
    """Encerra a sessao por tempo total ou por silencio.

    Motivo pratico: renderizacao de avatar e cobrada por minuto e continua
    correndo com o avatar calado. Uma sessao esquecida aberta e prejuizo puro.
    """

    def __init__(self, ctx: JobContext, max_minutes: int, silence_timeout_s: int):
        self._ctx = ctx
        self._max_seconds = max_minutes * 60
        self._silence_timeout = silence_timeout_s
        self._last_activity = time.monotonic()
        self._started = time.monotonic()
        self._task: asyncio.Task | None = None
        self.reason: str | None = None

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    def minutos_decorridos(self) -> float:
        """Quanto a sessao durou, em minutos. Serve para acertar a reserva."""
        return (time.monotonic() - self._started) / 60.0

    def start(self) -> None:
        self._task = asyncio.create_task(self._watch())

    def finish_now(self, reason: str) -> None:
        """Encerramento pedido pelo proprio fluxo do n8n."""
        if self.reason is None:
            self.reason = reason
        self._ctx.shutdown(reason=reason)

    async def _watch(self) -> None:
        try:
            while True:
                await asyncio.sleep(1.0)
                now = time.monotonic()

                if self._max_seconds and now - self._started >= self._max_seconds:
                    self.reason = "tempo_maximo"
                    break

                if (
                    self._silence_timeout
                    and now - self._last_activity >= self._silence_timeout
                ):
                    self.reason = "silencio"
                    break
        except asyncio.CancelledError:
            return

        logger.info("encerrando sessao motivo=%s", self.reason)
        self._ctx.shutdown(reason=self.reason or "limite")

    async def aclose(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


async def relatar_fim_de_sessao(room_name: str, minutos: float) -> None:
    """Avisa o token server quanto a conversa durou, para acertar os minutos.

    O token server reserva o pior caso (SESSION_MAX_MINUTES) ao emitir o
    token, porque ele nao tem como saber quando a conversa acaba. Este aviso
    devolve a diferenca.

    Falhar aqui nao pode derrubar o encerramento: no pior caso a reserva
    continua debitada, que e' o lado seguro de errar.
    """
    base = settings.token_server_internal_url.strip().rstrip("/")
    if not base or not settings.token_server_shared_secret:
        return

    try:
        import aiohttp

        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"{base}/session-ended",
                json={"room": room_name, "minutos": round(minutos, 2)},
                headers={"x-api-key": settings.token_server_shared_secret},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status != 200:
                    logger.warning(
                        "token server recusou o fim da sessao: %s %s",
                        r.status, (await r.text())[:200],
                    )
                else:
                    logger.info(
                        "fim de sessao informado room=%s minutos=%.1f", room_name, minutos
                    )
    except Exception:  # pragma: no cover - rede
        logger.exception("falha ao informar o fim da sessao %s", room_name)


def _first_participant_identity(room: object) -> str:
    try:
        participants = getattr(room, "remote_participants", {}) or {}
        for participant in participants.values():
            identity = getattr(participant, "identity", "")
            if identity:
                return str(identity)
    except Exception:  # pragma: no cover
        pass
    return ""


@server.rtc_session(agent_name=settings.agent_name)
async def iara_session(ctx: JobContext) -> None:
    room_name = getattr(ctx.room, "name", "?")
    engine = create_avatar_engine()
    logger.info("sessao iniciando room=%s engine=%s", room_name, engine.name)

    settings.require("n8n_webhook_url")

    recorder = TurnMetricsRecorder(
        room=room_name,
        engine=engine.name,
        log_path=settings.metrics_log_path or None,
    )
    limits = SessionLimits(
        ctx,
        max_minutes=settings.session_max_minutes,
        silence_timeout_s=settings.session_silence_timeout_s,
    )
    probe: AvatarVideoProbe | None = None

    # O session_id e' o nome da sala. E' unico por conversa e o n8n pode usa-lo
    # como chave de memoria do fluxo sem precisar inventar identificador.
    brain = N8nBrain(
        session_id=room_name,
        user_id=_first_participant_identity(ctx.room),
    )

    session = build_session()
    recorder.attach(session)

    agent = IaraAgent(
        brain,
        on_brain_reply=recorder.mark_brain,
        on_end_session=lambda: limits.finish_now("encerrado_pelo_fluxo"),
    )

    # qualquer sinal de vida do usuario zera o cronometro de silencio
    safe_on(session, "user_input_transcribed", lambda _ev: limits.touch())
    safe_on(session, "user_state_changed", lambda _ev: limits.touch())

    if settings.measure_avatar_video:
        probe = AvatarVideoProbe(ctx.room, recorder)
        probe.start()

    async def teardown() -> None:
        recorder.flush()
        logger.info(
            "session_summary %s",
            json.dumps(
                {**recorder.summary(), "motivo": limits.reason or "usuario"},
                ensure_ascii=False,
            ),
        )
        await limits.aclose()
        if probe is not None:
            await probe.aclose()
        await brain.aclose()
        await engine.aclose()
        await relatar_fim_de_sessao(room_name, limits.minutos_decorridos())

    ctx.add_shutdown_callback(teardown)

    # O avatar precisa entrar na sala antes de session.start(): e ele quem
    # assume a saida de audio da sessao. Invertendo a ordem, o agente publica
    # a propria voz e o usuario ouve o audio duas vezes, fora de sincronia.
    await engine.start(session, room=ctx.room)

    await session.start(
        room=ctx.room,
        agent=agent,
        room_options=room_io.RoomOptions(
            # o motor de avatar ja publica o audio junto com o video
            audio_output=not engine.publishes_room_audio,
        ),
    )

    limits.start()

    await wait_for_app_ready(ctx.room)
    await _greet(session, brain)


APP_READY_ATTRIBUTE = "app.avatar_ready"


async def wait_for_app_ready(room: object, timeout_s: float = 8.0) -> bool:
    """Espera o app avisar que ja esta recebendo o video do avatar.

    Sem isto o agente comeca a falar antes de o app assinar as faixas e o
    comeco da frase se perde - o usuario ouve a saudacao pela metade. Medido:
    a fala comecava ate 3,7 s antes da assinatura das faixas.

    E um handshake, nao um atraso fixo: em rede boa sai na hora, em rede ruim
    espera o necessario. Se o sinal nao vier dentro do timeout, fala assim
    mesmo - melhor uma saudacao cortada do que silencio.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            for participant in (getattr(room, "remote_participants", {}) or {}).values():
                attrs = getattr(participant, "attributes", {}) or {}
                if attrs.get(APP_READY_ATTRIBUTE):
                    return True
        except Exception:  # pragma: no cover
            pass
        await asyncio.sleep(0.1)

    logger.warning(
        "app nao sinalizou prontidao em %.1fs; falando assim mesmo", timeout_s
    )
    return False


async def _greet(session: object, brain: N8nBrain) -> None:
    """Primeira fala da sessao.

    `local` fala uma linha fixa na hora. `n8n` pede a abertura ao fluxo, o que
    faz sentido quando o roteiro clinico define como a conversa comeca - ao
    custo de uma ida ao n8n antes da primeira palavra.
    """
    if settings.greeting_mode == "n8n":
        try:
            reply = await brain.ask(settings.n8n_start_event)
            session.say(reply.text)  # type: ignore[attr-defined]
            return
        except BrainError as exc:
            logger.error("n8n falhou na saudacao, usando a local: %s", exc)

    session.say(settings.greeting_text)  # type: ignore[attr-defined]


if __name__ == "__main__":
    agents.cli.run_app(server)
