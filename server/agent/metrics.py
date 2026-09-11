"""Instrumentacao de latencia por turno.

Sem estes numeros nao existe base para escolher entre HeyGen e bitHuman.
Impressao visual nao decide; a mediana de t_total decide.

Marcos registrados por turno (ms):
    t_speech_end          fim da fala do usuario, detectado pelo endpointing
    t_stt_final           transcricao final disponivel
    t_llm_first_token     primeiro texto entregue ao TTS. Com o n8n como
                          cerebro isso costuma ser a frase de espera, nao a
                          resposta - por isso existe t_n8n_ms.
    t_tts_first_byte      primeiro byte de audio do ElevenLabs
    t_avatar_first_frame  primeiro frame de video do avatar apos o turno
    t_total               t_avatar_first_frame - t_speech_end
    t_n8n_ms              tempo de raciocinio do fluxo do n8n

Todos os marcos, exceto t_speech_end, sao relativos a t_speech_end.

Nota de implementacao: os nomes dos campos de metrica do SDK mudam entre
versoes menores. Em vez de casar por isinstance com classes que podem ser
renomeadas, este modulo le os campos por duck typing (ttft, ttfb,
end_of_utterance_delay). Se um campo sumir, o marco fica nulo e o resto do
turno continua sendo registrado, em vez de a sessao quebrar.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("iara.metrics")


@dataclass
class TurnMetrics:
    """Uma linha de telemetria por turno de conversa."""

    turn: int
    room: str
    engine: str

    # instante absoluto (epoch) do fim da fala, para correlacionar com logs
    t_speech_end_epoch: float | None = None

    # marcos relativos ao fim da fala, em ms
    t_stt_final: float | None = None
    t_llm_first_token: float | None = None
    t_tts_first_byte: float | None = None
    t_avatar_first_frame: float | None = None
    t_total: float | None = None

    # tempo que o fluxo do n8n levou pensando, medido de ponta a ponta da
    # chamada HTTP. E' o numero que importa quando t_total estoura: se
    # t_n8n_ms domina, o gargalo esta no workflow, nao no nosso pipeline.
    t_n8n_ms: float | None = None
    filler_used: bool = False

    # contexto util na hora de investigar um outlier
    interrupted: bool = False
    avatar_frame_source: str = "none"  # video | agent_state | none
    extra: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))


def _median(values: list[float | None]) -> float | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return round((clean[mid - 1] + clean[mid]) / 2, 1)


class TurnMetricsRecorder:
    """Acumula os marcos de um turno e emite uma linha JSON ao fecha-lo.

    Uso: instancie uma vez por sessao e chame `attach(session)`.
    """

    def __init__(self, room: str, engine: str, log_path: str | None = None) -> None:
        self._room = room
        self._engine = engine
        self._turn_index = 0
        self._current: TurnMetrics | None = None
        self._speech_end_mono: float | None = None
        self._closed = True
        self._path = Path(log_path) if log_path else None
        self.history: list[TurnMetrics] = []

        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    # -- ciclo de vida do turno -----------------------------------------

    def start_turn(self, end_of_utterance_delay: float | None = None) -> None:
        """Abre um turno. `end_of_utterance_delay` recua o t0 ate o fim real da fala."""
        self.flush()  # um turno novo fecha o anterior, mesmo que incompleto

        now = time.monotonic()
        self._speech_end_mono = now - (end_of_utterance_delay or 0.0)
        self._turn_index += 1
        self._closed = False
        self._current = TurnMetrics(
            turn=self._turn_index,
            room=self._room,
            engine=self._engine,
            t_speech_end_epoch=time.time() - (end_of_utterance_delay or 0.0),
        )

    def _since_speech_end(self) -> float | None:
        if self._speech_end_mono is None:
            return None
        return round((time.monotonic() - self._speech_end_mono) * 1000.0, 1)

    def mark(self, field_name: str, value_ms: float | None = None) -> None:
        """Registra um marco. Sem valor, usa o relogio atual."""
        if self._current is None or self._closed:
            return
        current = getattr(self._current, field_name, "__missing__")
        if current != "__missing__" and current is not None:
            return  # primeiro vence; um turno tem um unico "primeiro token"
        setattr(
            self._current,
            field_name,
            value_ms if value_ms is not None else self._since_speech_end(),
        )

    def mark_avatar_frame(self, source: str) -> None:
        if self._current is None or self._closed:
            return
        if self._current.t_avatar_first_frame is not None:
            return
        self._current.t_avatar_first_frame = self._since_speech_end()
        self._current.t_total = self._current.t_avatar_first_frame
        self._current.avatar_frame_source = source

    def mark_brain(self, latency_ms: float, used_filler: bool) -> None:
        """Registra a ida ao n8n e se foi preciso encher o silencio."""
        if self._current is None or self._closed:
            return
        self._current.t_n8n_ms = round(latency_ms, 1)
        self._current.filler_used = used_filler

    def mark_interrupted(self) -> None:
        if self._current is not None and not self._closed:
            self._current.interrupted = True

    def flush(self) -> TurnMetrics | None:
        """Fecha o turno corrente e emite a linha JSON."""
        if self._current is None or self._closed:
            return None
        self._closed = True
        turn = self._current
        self.history.append(turn)
        line = turn.as_json()
        logger.info("turn_metrics %s", line)
        if self._path is not None:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                logger.exception("nao foi possivel escrever %s", self._path)
        return turn

    # -- resumo da sessao -----------------------------------------------

    def summary(self) -> dict[str, Any]:
        totals = [t.t_total for t in self.history if t.t_total is not None]
        totals.sort()

        def pct(p: float) -> float | None:
            if not totals:
                return None
            idx = min(len(totals) - 1, int(round((len(totals) - 1) * p)))
            return totals[idx]

        return {
            "room": self._room,
            "engine": self._engine,
            "turns": len(self.history),
            "turns_medidos": len(totals),
            "t_total_p50_ms": pct(0.50),
            "t_total_p90_ms": pct(0.90),
            "t_total_max_ms": totals[-1] if totals else None,
            "interrupcoes": sum(1 for t in self.history if t.interrupted),
            "turnos_com_enchimento": sum(1 for t in self.history if t.filler_used),
            "t_n8n_p50_ms": _median([t.t_n8n_ms for t in self.history]),
        }

    # -- ligacao com a AgentSession -------------------------------------

    def attach(self, session: Any) -> None:
        """Assina os eventos da AgentSession e alimenta os marcos.

        Tolerante a versao: um evento que nao exista no SDK instalado apenas
        deixa o marco correspondente nulo.
        """

        def on_metrics(ev: Any) -> None:
            m = getattr(ev, "metrics", ev)

            eou = getattr(m, "end_of_utterance_delay", None)
            if eou is not None:
                # fim de turno detectado: abre o turno com t0 no fim real da fala
                self.start_turn(end_of_utterance_delay=float(eou))
                transcription_delay = getattr(m, "transcription_delay", None)
                if transcription_delay is not None:
                    self.mark(
                        "t_stt_final",
                        max(0.0, (float(eou) - float(transcription_delay))) * 1000.0,
                    )
                return

            ttft = getattr(m, "ttft", None)
            if ttft is not None and ttft >= 0:
                self.mark("t_llm_first_token")
                return

            ttfb = getattr(m, "ttfb", None)
            if ttfb is not None and ttfb >= 0:
                self.mark("t_tts_first_byte")
                return

        def on_user_transcript(ev: Any) -> None:
            if getattr(ev, "is_final", False):
                self.mark("t_stt_final")

        def on_agent_state(ev: Any) -> None:
            new_state = getattr(ev, "new_state", None)
            if new_state == "speaking":
                # proxy: o avatar comecou a reproduzir. So conta se o probe de
                # video nao tiver registrado o frame real antes.
                self.mark_avatar_frame("agent_state")
            elif new_state == "listening":
                self.flush()

        def on_interruption(_ev: Any) -> None:
            self.mark_interrupted()

        safe_on(session, "metrics_collected", on_metrics)
        safe_on(session, "user_input_transcribed", on_user_transcript)
        safe_on(session, "agent_state_changed", on_agent_state)
        safe_on(session, "user_interruption_detected", on_interruption)


def safe_on(emitter: Any, event: str, handler: Any) -> None:
    try:
        emitter.on(event, handler)
    except Exception:  # pragma: no cover - evento inexistente nesta versao
        logger.warning("evento %r indisponivel nesta versao do SDK", event)


class AvatarVideoProbe:
    """Mede t_avatar_first_frame de verdade, lendo a faixa de video do avatar.

    Custa CPU (decodifica video no processo do agente), entao fica atras de
    MEASURE_AVATAR_VIDEO. Ligue para comparar HeyGen x bitHuman, desligue
    depois. Se nao conseguir assinar a faixa, o recorder cai no proxy
    agent_state_changed e o campo avatar_frame_source indica qual foi usado.
    """

    def __init__(self, room: Any, recorder: TurnMetricsRecorder) -> None:
        self._room = room
        self._recorder = recorder
        self._tasks: set[Any] = set()

    def start(self) -> None:
        import asyncio

        from livekit import rtc

        def on_track_subscribed(track: Any, *_args: Any) -> None:
            if track.kind != rtc.TrackKind.KIND_VIDEO:
                return

            async def pump() -> None:
                stream = rtc.VideoStream(track)
                try:
                    async for _frame in stream:
                        self._recorder.mark_avatar_frame("video")
                finally:
                    await stream.aclose()

            task = asyncio.create_task(pump())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        def on_track_published(publication: Any, *_args: Any) -> None:
            if getattr(publication, "kind", None) == rtc.TrackKind.KIND_VIDEO:
                try:
                    publication.set_subscribed(True)
                except Exception:  # pragma: no cover
                    logger.debug("nao foi possivel assinar a faixa de video")

        safe_on(self._room, "track_subscribed", on_track_subscribed)
        safe_on(self._room, "track_published", on_track_published)
        logger.info("probe de video do avatar ativo")

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
