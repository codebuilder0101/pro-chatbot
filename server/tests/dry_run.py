"""Dry-run do agente, sem credencial de verdade e sem sala LiveKit.

Objetivo: executar o codigo contra o SDK instalado, nao so' conferir sintaxe.
Um erro de assinatura de plugin, um import errado ou uma mudanca de API do
livekit-agents aparece aqui, e nao na frente do cliente.

O que ele faz:
  1. importa todos os modulos do projeto
  2. constroi STT, TTS, VAD, detector de turno e a AgentSession sem LLM
  3. sobe um webhook falso em localhost e roda o llm_node de verdade,
     medindo se a frase de espera sai na hora certa
  4. verifica que barge-in cancela a requisicao ao n8n

    python tests/dry_run.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Chaves falsas: nenhuma chamada externa e' feita neste teste. Precisam existir
# apenas porque os plugins validam presenca no construtor.
os.environ.setdefault("LIVEKIT_URL", "ws://localhost:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "secret")
os.environ.setdefault("DEEPGRAM_API_KEY", "dry-run")
os.environ.setdefault("ELEVENLABS_API_KEY", "dry-run")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "dry-run-voice")
os.environ.setdefault("HEYGEN_API_KEY", "dry-run")
os.environ.setdefault("HEYGEN_AVATAR_ID", "dry-run-avatar")
os.environ.setdefault("TOKEN_SERVER_SHARED_SECRET", "dry-run")
os.environ.setdefault("TURN_DETECTOR", "vad")  # nao baixa modelo
# Estes tres sao imposicao, nao padrao. Dentro do container o .env de
# producao ja esta no ambiente, e um setdefault deixaria o teste bater no
# fluxo real do cliente no n8n - disparando um atendimento de mentira.
os.environ["N8N_WEBHOOK_URL"] = "http://127.0.0.1:8765/webhook"
os.environ["N8N_AUTH_TOKEN"] = ""
os.environ["N8N_FILLER_AFTER_S"] = "0.4"
os.environ["N8N_SECOND_FILLER_AFTER_S"] = "1.0"

# ---------------------------------------------------------------------------
# Contorno especifico DESTA maquina, nao do projeto.
#
# O binario nativo livekit-local-inference nao roda neste Xeon E3-1270 v3
# (Haswell, sem AVX-512): qualquer versao dele derruba o processo com
# segfault, e como livekit.agents o importa no nivel de pacote, nem o import
# passa. Aqui ele e substituido por um stub para o resto poder ser exercitado.
#
# O que isso deixa de fora: o VAD nativo e o detector de fim de turno da
# LiveKit Inference. Nada disso esta no caminho testado - a configuracao usa
# TURN_DETECTOR=vad com o Silero, que roda em onnxruntime de verdade.
# Num host de producao com CPU recente o stub e desnecessario.
import subprocess as _sp
import types as _types

# A sonda roda num subprocesso porque um segfault mata o interpretador: nao
# adianta envolver o import num try/except.
_probe = _sp.run(
    [sys.executable, "-c", "import livekit.local_inference"],
    capture_output=True,
)
if _probe.returncode != 0:
    _stub = _types.ModuleType("livekit.local_inference")
    _stub.VAD = type("VAD", (), {})
    _stub.EOT = type("EOT", (), {})
    _stub.VAD_WINDOW_SAMPLES = 512
    _stub.init_vad = lambda *a, **k: None
    _stub.init_eot = lambda *a, **k: None
    sys.modules["livekit.local_inference"] = _stub
    print(
        "  aviso   livekit.local_inference nao roda nesta CPU "
        f"(codigo {_probe.returncode}); usando stub"
    )

PASS = "  ok      "
FAIL = "  FALHOU  "

results: list[bool] = []


def check(label: str, fn) -> object:
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL}{label}: {type(exc).__name__}: {exc}")
        results.append(False)
        return None
    print(f"{PASS}{label}")
    results.append(True)
    return value


# ---------------------------------------------------------------- imports
print("--- imports ---")
check("livekit-agents importa", lambda: __import__("livekit.agents"))
check("agent.config", lambda: __import__("agent.config", fromlist=["settings"]))
check("agent.n8n", lambda: __import__("agent.n8n", fromlist=["N8nBrain"]))
check("agent.metrics", lambda: __import__("agent.metrics", fromlist=["TurnMetricsRecorder"]))
check("agent.avatar", lambda: __import__("agent.avatar", fromlist=["create_avatar_engine"]))
check("agent.pipeline", lambda: __import__("agent.pipeline", fromlist=["build_session"]))
check("agent.agent (entrypoint)", lambda: __import__("agent.agent", fromlist=["server"]))
check("token_server.main", lambda: __import__("token_server.main", fromlist=["app"]))

import livekit.agents as lkagents  # noqa: E402

from agent import pipeline  # noqa: E402
from agent.avatar import create_avatar_engine  # noqa: E402
from agent.metrics import TurnMetricsRecorder  # noqa: E402
from agent.n8n import N8nBrain  # noqa: E402

print(f"\n  livekit-agents {lkagents.__version__}\n")

# ------------------------------------------------------------ construcao
print("--- construcao dos componentes ---")
check("Deepgram STT", pipeline.build_stt)
check("ElevenLabs TTS", pipeline.build_tts)
check("detector de fim de turno", pipeline._build_turn_detection)
check("persona carrega", pipeline.load_persona)
session = check("AgentSession sem llm=", pipeline.build_session)
engine = check("motor de avatar (factory)", create_avatar_engine)
check("recorder de metricas", lambda: TurnMetricsRecorder(room="dry", engine="heygen"))

def _assert(cond: bool, msg: str) -> bool:
    if not cond:
        raise AssertionError(msg)
    return True


if session is not None:
    check("session.llm e' None", lambda: _assert(session.llm is None, "llm deveria ser None"))


# --------------------------------------------------- webhook falso do n8n
class FakeN8n:
    """Servidor minimo que responde depois de um atraso controlado."""

    def __init__(self) -> None:
        self.delay = 0.0
        self.requests: list[dict] = []
        self.cancelled = 0
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 8765)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            length = 0
            for line in head.decode("latin1").split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1].strip())
            raw = await reader.readexactly(length) if length else b"{}"
            self.requests.append(json.loads(raw))

            # Corrida entre o atraso simulado e o fim da conexao. Descobrir o
            # corte so' na hora de escrever nao funciona: o socket local aceita
            # a escrita e o teste passaria sem medir nada.
            eof = asyncio.create_task(reader.read(1))
            delay = asyncio.create_task(asyncio.sleep(self.delay))
            done, pending = await asyncio.wait(
                {eof, delay}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if eof in done:
                # cliente foi embora antes da resposta: e' o caso de barge-in
                self.cancelled += 1
                return

            body = json.dumps({"output": "Resposta do fluxo clinico."}).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n"
                b"content-length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            )
            await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError, asyncio.IncompleteReadError):
            # o cliente desistiu no meio: e' o caso de barge-in
            self.cancelled += 1
        finally:
            writer.close()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


async def collect(agent, text: str) -> tuple[list[str], float]:
    """Roda o llm_node e devolve os pedacos com o instante de cada um."""
    from livekit.agents import llm as lkllm

    ctx = lkllm.ChatContext.empty()
    ctx.add_message(role="user", content=text)

    started = time.monotonic()
    chunks: list[str] = []
    timings: list[float] = []
    async for chunk in agent.llm_node(ctx, [], None):
        if isinstance(chunk, str):
            chunks.append(chunk)
            timings.append(time.monotonic() - started)
    return chunks, timings[0] if timings else -1.0


async def scenarios() -> None:
    print("\n--- llm_node contra um n8n falso ---")
    fake = FakeN8n()
    await fake.start()

    try:
        brain = N8nBrain(session_id="dry-room", user_id="tester")
        agent = pipeline.IaraAgent(brain)

        # 1. fluxo rapido: nenhuma frase de espera
        fake.delay = 0.05
        chunks, first_at = await collect(agent, "Bom dia.")
        _report(
            "fluxo rapido nao dispara frase de espera",
            chunks == ["Resposta do fluxo clinico."],
            f"pedacos={chunks}",
        )

        # 2. fluxo lento: frase de espera antes da resposta
        fake.delay = 0.8
        chunks, first_at = await collect(agent, "Estou com dor de cabeca.")
        _report(
            "fluxo lento dispara a frase de espera",
            len(chunks) == 2 and chunks[-1] == "Resposta do fluxo clinico.",
            f"pedacos={chunks}",
        )
        _report(
            f"a frase de espera sai perto de 0,4s (saiu em {first_at:.2f}s)",
            0.3 <= first_at <= 0.7,
            f"first_at={first_at:.3f}",
        )

        # 3. fluxo muito lento: segunda frase de espera
        fake.delay = 1.8
        chunks, _ = await collect(agent, "E se piorar?")
        _report(
            "fluxo muito lento dispara a segunda frase",
            len(chunks) == 3,
            f"pedacos={chunks}",
        )

        # 4. as frases nao se repetem em sequencia
        fake.delay = 0.8
        seen = []
        for _ in range(4):
            chunks, _ = await collect(agent, "pergunta")
            seen.append(chunks[0])
        _report(
            "frase de espera nao repete a anterior",
            all(seen[i] != seen[i + 1] for i in range(len(seen) - 1)),
            f"sequencia={seen}",
        )

        # 5. barge-in cancela a requisicao em voo
        fake.delay = 5.0
        before = fake.cancelled

        async def run_and_cancel() -> None:
            from livekit.agents import llm as lkllm

            ctx = lkllm.ChatContext.empty()
            ctx.add_message(role="user", content="vou interromper")
            gen = agent.llm_node(ctx, [], None)
            await gen.__anext__()  # consome a frase de espera
            await gen.aclose()  # barge-in

        await run_and_cancel()
        await asyncio.sleep(0.4)
        _report(
            "barge-in derruba a chamada ao n8n",
            fake.cancelled > before,
            f"conexoes abortadas: {fake.cancelled - before}",
        )

        # 6. o payload leva o que o n8n precisa
        payload = fake.requests[0]
        _report(
            "payload tem session_id, text, turn e history",
            all(k in payload for k in ("session_id", "text", "turn", "history", "locale")),
            f"chaves={sorted(payload)}",
        )

        # 7. as frases de espera nao vao para o historico do n8n
        historico = fake.requests[-1].get("history", [])
        assistentes = [h["content"] for h in historico if h["role"] == "assistant"]
        _report(
            "historico enviado nao contem frase de espera",
            all(a == "Resposta do fluxo clinico." for a in assistentes),
            f"assistente={assistentes}",
        )

        # 8. n8n fora do ar: fala a frase de falha, nao quebra
        await fake.stop()
        chunks, _ = await collect(agent, "alguem ai?")
        from agent.config import settings

        _report(
            "n8n fora do ar termina na frase de falha",
            chunks[-1] == settings.brain_failure_text,
            f"pedacos={chunks}",
        )
        _report(
            "frase de falha nunca vaza detalhe tecnico",
            not any(
                termo in chunks[-1].lower()
                for termo in ("http", "error", "exception", "traceback", "127.0.0.1")
            ),
            f"texto={chunks[-1]!r}",
        )

        await brain.aclose()
    finally:
        await fake.stop()


def _report(label: str, ok: bool, detail: str = "") -> None:
    print(f"{PASS if ok else FAIL}{label}" + ("" if ok else f"  <- {detail}"))
    results.append(ok)


if __name__ == "__main__":
    asyncio.run(scenarios())
    total = len(results)
    bad = results.count(False)
    print(f"\n{total - bad}/{total} passaram")
    sys.exit(1 if bad else 0)
