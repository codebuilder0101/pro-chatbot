"""Testa o parser de resposta do n8n.

Roda sem instalar nada: as unicas dependencias externas de agent/n8n.py no
nivel de modulo sao aiohttp e python-dotenv, e as duas sao substituidas por
stubs aqui. Sem rede, sem LiveKit.

    python tests/test_n8n_parse.py

Para que serve na pratica: quando o fluxo do n8n mudar o no' final e a IARA
comecar a responder a frase de falha, rode isto com o formato novo. Se passar,
o problema nao esta no parser.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- stubs ---------------------------------------------------------------
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: False
sys.modules["dotenv"] = _dotenv

_aiohttp = types.ModuleType("aiohttp")
_aiohttp.ClientTimeout = type("ClientTimeout", (), {"__init__": lambda self, **k: None})
_aiohttp.ClientSession = object
_aiohttp.ClientError = Exception
sys.modules["aiohttp"] = _aiohttp

from agent.n8n import BrainError, _parse_reply  # noqa: E402

JSON = "application/json"
TEXT = "text/plain; charset=utf-8"

# (descricao, corpo, content-type, texto esperado, end_session esperado)
CASES = [
    ("chave reply", {"reply": "Bom dia."}, JSON, "Bom dia.", False),
    ("chave text", {"text": "Bom dia."}, JSON, "Bom dia.", False),
    ("chave output (AI Agent)", {"output": "Bom dia."}, JSON, "Bom dia.", False),
    ("chave message", {"message": "Bom dia."}, JSON, "Bom dia.", False),
    ("chave answer", {"answer": "Bom dia."}, JSON, "Bom dia.", False),
    ("lista (Respond to Webhook)", [{"output": "Bom dia."}], JSON, "Bom dia.", False),
    ("lista de strings", ["Bom dia."], JSON, "Bom dia.", False),
    ("string crua em json", "Bom dia.", JSON, "Bom dia.", False),
    ("corpo text/plain", "Bom dia.", TEXT, "Bom dia.", False),
    ("aninhado em json", {"json": {"output": "Bom dia."}}, JSON, "Bom dia.", False),
    ("output aninhado", {"output": {"text": "Bom dia."}}, JSON, "Bom dia.", False),
    ("espacos sobrando", {"reply": "  Bom dia.  "}, JSON, "Bom dia.", False),
    ("end_session", {"reply": "Ate mais.", "end_session": True}, JSON, "Ate mais.", True),
    ("endSession camelCase", {"reply": "Ate.", "endSession": True}, JSON, "Ate.", True),
    (
        "end_session dentro de json",
        {"json": {"reply": "Ate.", "end_session": True}},
        JSON,
        "Ate.",
        True,
    ),
    (
        "lista com item aninhado em json",
        [{"json": {"reply": "Bom dia."}}],
        JSON,
        "Bom dia.",
        False,
    ),
]

# Formatos que precisam ser rejeitados: melhor a IARA dizer que teve um
# problema do que ler em voz alta um pedaco de JSON.
FAILURES = [
    ("dict sem chave util", {"foo": "bar"}, JSON),
    ("lista vazia", [], JSON),
    ("string vazia", "", JSON),
    ("texto vazio", "   ", TEXT),
    ("reply vazio", {"reply": "   "}, JSON),
    ("numero", 42, JSON),
]


def main() -> int:
    ok = fail = 0

    for desc, body, ct, expected, expected_end in CASES:
        try:
            text, end_session, _ = _parse_reply(body, ct)
        except Exception as exc:  # noqa: BLE001
            print(f"  FALHOU  {desc}: levantou {exc!r}")
            fail += 1
            continue
        if text != expected:
            print(f"  FALHOU  {desc}: esperava {expected!r}, veio {text!r}")
            fail += 1
        elif end_session != expected_end:
            print(
                f"  FALHOU  {desc}: end_session esperava "
                f"{expected_end}, veio {end_session}"
            )
            fail += 1
        else:
            print(f"  ok      {desc}")
            ok += 1

    print()
    for desc, body, ct in FAILURES:
        try:
            _parse_reply(body, ct)
        except BrainError:
            print(f"  ok      rejeita: {desc}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FALHOU  {desc}: erro errado {type(exc).__name__}: {exc}")
            fail += 1
        else:
            print(f"  FALHOU  {desc}: deveria ter rejeitado")
            fail += 1

    print(f"\n{ok} passaram, {fail} falharam")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
