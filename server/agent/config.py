"""Leitura e normalizacao de variaveis de ambiente.

Os nomes exigidos pela especificacao nem sempre sao os nomes que os plugins
oficiais leem. Este modulo faz o alias de uma vez, no boot, para que nenhum
outro arquivo precise saber disso.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

# --- aliases: nome da spec -> nome que o plugin realmente le -------------
_ALIASES = {
    "ELEVENLABS_API_KEY": "ELEVEN_API_KEY",
    "HEYGEN_API_KEY": "LIVEAVATAR_API_KEY",
    "HEYGEN_AVATAR_ID": "LIVEAVATAR_AVATAR_ID",
    "BITHUMAN_API_KEY": "BITHUMAN_API_SECRET",
}

for _src, _dst in _ALIASES.items():
    _v = os.environ.get(_src)
    if _v and not os.environ.get(_dst):
        os.environ[_dst] = _v


def _s(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _i(name: str, default: int) -> int:
    raw = _s(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _f(name: str, default: float) -> float:
    raw = _s(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _b(name: str, default: bool = False) -> bool:
    raw = _s(name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _list(name: str, default: list[str]) -> list[str]:
    """Lista separada por `|`. Barra vertical porque as frases tem virgula."""
    raw = _s(name)
    if not raw:
        return default
    items = [p.strip() for p in raw.split("|")]
    return [p for p in items if p] or default


# Frases de espera. Curtas de proposito: elas existem para cobrir o silencio
# enquanto o n8n pensa, nao para preencher tempo. Uma frase longa atrasaria a
# resposta de verdade, que pode chegar no meio dela.
_FILLERS = [
    "Deixa eu ver aqui.",
    "So um segundo.",
    "Deixa eu conferir.",
    "Um instante.",
]

_FILLERS_LONG = [
    "Ainda estou verificando, ja te respondo.",
    "So mais um pouquinho, estou terminando de olhar.",
]


@dataclass(frozen=True)
class Settings:
    # LiveKit
    livekit_url: str = field(default_factory=lambda: _s("LIVEKIT_URL"))
    livekit_api_key: str = field(default_factory=lambda: _s("LIVEKIT_API_KEY"))
    livekit_api_secret: str = field(default_factory=lambda: _s("LIVEKIT_API_SECRET"))
    agent_name: str = field(default_factory=lambda: _s("AGENT_NAME", "iara"))

    # STT
    deepgram_model: str = field(default_factory=lambda: _s("DEEPGRAM_MODEL", "nova-3"))
    stt_language: str = field(default_factory=lambda: _s("STT_LANGUAGE", "pt-BR"))

    # TTS
    elevenlabs_voice_id: str = field(default_factory=lambda: _s("ELEVENLABS_VOICE_ID"))
    elevenlabs_model: str = field(
        default_factory=lambda: _s("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
    )
    tts_language: str = field(default_factory=lambda: _s("TTS_LANGUAGE", "pt"))

    # Termos que o Deepgram deve reconhecer com grafia certa. Sem isto ele
    # transcreve "IARA" como "Yara" - foneticamente certo, grafia errada, e
    # o fluxo do n8n recebe um nome que nao e o da assistente. Medido.
    #
    # So funciona com nova-3 (keyterm). Em nova-2 o parametro e outro.
    stt_keyterms: list[str] = field(
        default_factory=lambda: _list("STT_KEYTERMS", ["IARA", "Ayo"])
    )

    # inference | multilingual | vad
    turn_detector: str = field(default_factory=lambda: _s("TURN_DETECTOR", "inference"))

    # --- cerebro: n8n ---------------------------------------------------
    n8n_webhook_url: str = field(default_factory=lambda: _s("N8N_WEBHOOK_URL"))
    n8n_auth_header: str = field(
        default_factory=lambda: _s("N8N_AUTH_HEADER", "x-iara-token")
    )
    n8n_auth_token: str = field(default_factory=lambda: _s("N8N_AUTH_TOKEN"))
    n8n_timeout_s: float = field(default_factory=lambda: _f("N8N_TIMEOUT_S", 30.0))
    n8n_history_turns: int = field(
        default_factory=lambda: _i("N8N_HISTORY_TURNS", 10)
    )

    # Espera antes da primeira frase de enchimento. Abaixo de ~0,5 s a IARA
    # fala "deixa eu ver" em cima de resposta que ja estava chegando.
    n8n_filler_after_s: float = field(
        default_factory=lambda: _f("N8N_FILLER_AFTER_S", 0.7)
    )
    # Espera adicional antes da segunda frase. 0 desliga a segunda.
    n8n_second_filler_after_s: float = field(
        default_factory=lambda: _f("N8N_SECOND_FILLER_AFTER_S", 4.0)
    )
    filler_phrases: list[str] = field(
        default_factory=lambda: _list("FILLER_PHRASES", _FILLERS)
    )
    filler_phrases_long: list[str] = field(
        default_factory=lambda: _list("FILLER_PHRASES_LONG", _FILLERS_LONG)
    )
    brain_failure_text: str = field(
        default_factory=lambda: _s(
            "BRAIN_FAILURE_TEXT",
            "Tive um problema aqui do meu lado e nao consegui buscar a "
            "resposta. Pode repetir?",
        )
    )

    # Saudacao: local (fixa, instantanea) ou n8n (o fluxo decide a abertura).
    greeting_mode: str = field(
        default_factory=lambda: _s("GREETING_MODE", "local").lower()
    )
    greeting_text: str = field(
        default_factory=lambda: _s(
            "GREETING_TEXT", "Oi! Eu sou a IARA. Como posso te ajudar?"
        )
    )
    n8n_start_event: str = field(
        default_factory=lambda: _s("N8N_START_EVENT", "__inicio__")
    )

    # Avatar
    avatar_engine: str = field(
        default_factory=lambda: _s("AVATAR_ENGINE", "heygen").lower()
    )

    # Sessao
    session_max_minutes: int = field(
        default_factory=lambda: _i("SESSION_MAX_MINUTES", 20)
    )
    session_silence_timeout_s: int = field(
        default_factory=lambda: _i("SESSION_SILENCE_TIMEOUT_S", 90)
    )

    # Porta do servidor HTTP de saude do worker. O padrao do SDK e 8081, que
    # num VPS compartilhado costuma ja ser de outro servico - no nosso e do
    # nginx. Sem isto o agente sobe e morre com "address already in use".
    agent_http_port: int = field(default_factory=lambda: _i("AGENT_HTTP_PORT", 8081))
    # Vazio = todas as interfaces (padrao do SDK). Em maquina publica,
    # 127.0.0.1 evita expor o endpoint de saude.
    agent_http_host: str = field(default_factory=lambda: _s("AGENT_HTTP_HOST"))

    # Token server
    token_server_shared_secret: str = field(
        default_factory=lambda: _s("TOKEN_SERVER_SHARED_SECRET")
    )
    token_ttl_minutes: int = field(default_factory=lambda: _i("TOKEN_TTL_MINUTES", 25))

    # Instrumentacao
    measure_avatar_video: bool = field(
        default_factory=lambda: _b("MEASURE_AVATAR_VIDEO", False)
    )
    metrics_log_path: str = field(default_factory=lambda: _s("METRICS_LOG_PATH"))

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n, "")]
        if missing:
            raise RuntimeError(
                "Variaveis de ambiente obrigatorias ausentes: " + ", ".join(missing)
            )


settings = Settings()
