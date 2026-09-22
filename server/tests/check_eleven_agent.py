"""Diagnostico do agente do ElevenLabs usado pelo LiveAvatar (modo LITE).

Contexto: o LiveAvatar (app.liveavatar.com) consegue usar um agente do
ElevenLabs Agents como cerebro + voz. Nesse arranjo o LiveAvatar captura o
microfone, entrega o audio ao agente via LiveKit, e o agente faz STT, LLM e
TTS. O LiveAvatar so' anima o rosto com o audio que volta.

O que precisa estar certo do lado do ElevenLabs (documentacao oficial em
https://elevenlabs.io/docs/eleven-agents/guides/integrations/live-avatar):

  - Voice settings > TTS output format ............ PCM 24000 Hz
  - Advanced > User input audio format ............ PCM 24000 Hz
  - plano pago (chave do plano free e' bloqueada para uso por terceiros)
  - chave de API com convai_read, user_read e voices_read

Este script le o agente pela API e imprime o que esta fora do lugar. Depois
lista as ultimas conversas do agente: cada sessao do LiveAvatar que de fato
conectou ao agente aparece aqui como uma conversa (ate' uma recusada por
policy do ElevenLabs aparece). Se uma sessao foi aberta no LiveAvatar e
nenhuma conversa nova surgiu, o worker do conector ElevenLabs do LiveAvatar
nem abriu o WebSocket: o problema esta do lado do LiveAvatar, e nao no
microfone, na chave nem no agente. Em 18/09/2026 foi exatamente isso, com
chave, plano e formatos todos certos (verificado abrindo o WebSocket do
agente na mao com a mesma chave). Contorno: voice agent nativo do LiveAvatar
(modo FULL) com o mesmo prompt.

    python tests/check_eleven_agent.py agent_xxx
    python tests/check_eleven_agent.py agent_xxx --fix    # corrige os formatos

Le ELEVENLABS_API_KEY do ambiente ou do .env/.env.local, como o agente.
Sem --fix nao altera nada.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env.local")
load_dotenv(".env")

API = "https://api.elevenlabs.io/v1"
FORMATO = "pcm_24000"
# Origens que o ElevenLabs registra em metadata.conversation_initiation_source.
# react_sdk/js_sdk = widget "Test agent" do proprio painel do ElevenLabs.
ORIGEM_PAINEL = {"react_sdk", "js_sdk", "widget"}


def _req(method: str, path: str, body: dict | None = None) -> dict:
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY nao definida (ambiente ou .env).")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} em {method} {path}: {e.read().decode()[:300]}")


def _hora(unix: int) -> str:
    return datetime.fromtimestamp(unix, timezone.utc).astimezone().strftime("%d/%m %H:%M")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fix = "--fix" in sys.argv
    if not args:
        agentes = _req("GET", "/convai/agents?page_size=30").get("agents", [])
        print("Informe o agent_id. Agentes da conta:")
        for a in agentes:
            print(f"  {a['agent_id']}  {a.get('name')}")
        return 2
    agent_id = args[0]

    problemas: list[str] = []

    # --- plano -------------------------------------------------------------
    sub = _req("GET", "/user/subscription")
    tier = sub.get("tier")
    print(f"plano ElevenLabs: {tier} ({sub.get('status')})")
    if tier in (None, "free"):
        problemas.append("plano free: o LiveAvatar recusa chave do plano free")

    # --- agente ------------------------------------------------------------
    ag = _req("GET", f"/convai/agents/{agent_id}")
    cc = ag.get("conversation_config", {})
    tts_fmt = cc.get("tts", {}).get("agent_output_audio_format")
    asr_fmt = cc.get("asr", {}).get("user_input_audio_format")
    auth = ag.get("platform_settings", {}).get("auth", {})
    print(f"agente: {ag.get('name')} ({agent_id})")
    print(f"  idioma ............... {cc.get('agent', {}).get('language')}")
    print(f"  primeira mensagem .... {cc.get('agent', {}).get('first_message')!r}")
    print(f"  LLM .................. {cc.get('agent', {}).get('prompt', {}).get('llm')}")
    print(f"  voz / modelo TTS ..... {cc['tts'].get('voice_id')} / {cc['tts'].get('model_id')}")
    print(f"  TTS output format .... {tts_fmt}")
    print(f"  user input format .... {asr_fmt}")
    print(f"  autenticacao ......... {'ligada' if auth.get('enable_auth') else 'desligada (publico)'}")
    if tts_fmt != FORMATO:
        problemas.append(f"TTS output format e' {tts_fmt}, precisa ser {FORMATO}")
    if asr_fmt != FORMATO:
        problemas.append(f"user input format e' {asr_fmt}, precisa ser {FORMATO}")

    # Nome duplicado nao quebra nada, mas ja causou confusao no dropdown do
    # LiveAvatar, que mostra so' o nome.
    homonimos = [
        a["agent_id"]
        for a in _req("GET", "/convai/agents?page_size=30").get("agents", [])
        if a.get("name") == ag.get("name") and a["agent_id"] != agent_id
    ]
    if homonimos:
        print(f"  aviso: outro(s) agente(s) com o mesmo nome: {', '.join(homonimos)}")

    if fix and (tts_fmt != FORMATO or asr_fmt != FORMATO):
        _req(
            "PATCH",
            f"/convai/agents/{agent_id}",
            {
                "conversation_config": {
                    "tts": {"agent_output_audio_format": FORMATO},
                    "asr": {"user_input_audio_format": FORMATO},
                }
            },
        )
        print(f"  -> formatos corrigidos para {FORMATO}")
        problemas = [p for p in problemas if "format" not in p]

    # --- conversas: a prova de que o LiveAvatar chegou ao agente -------------
    convs = _req(
        "GET", f"/convai/conversations?agent_id={agent_id}&page_size=10"
    ).get("conversations", [])
    print(f"ultimas conversas do agente ({len(convs)}):")
    fora_do_painel = 0
    for c in convs:
        det = _req("GET", f"/convai/conversations/{c['conversation_id']}")
        origem = det.get("metadata", {}).get("conversation_initiation_source") or "?"
        if origem not in ORIGEM_PAINEL:
            fora_do_painel += 1
        print(
            f"  {_hora(c.get('start_time_unix_secs', 0))}  {c.get('call_duration_secs', 0):>4}s"
            f"  {c.get('message_count', 0):>3} msgs  origem={origem}  {c.get('status')}"
        )
    if not convs:
        print("  nenhuma - o agente nunca recebeu uma conversa")
    elif fora_do_painel == 0:
        print(
            "  todas vieram do widget de teste do painel do ElevenLabs. Nenhuma sessao\n"
            "  do LiveAvatar chegou ao agente: se uma sessao foi aberta la e nao\n"
            "  apareceu aqui, o worker do LiveAvatar nem abriu o WebSocket - a falha\n"
            "  e' do lado do LiveAvatar, nao do microfone, da chave nem do agente."
        )

    print()
    if problemas:
        print("PROBLEMAS:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("agente OK para o LiveAvatar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
