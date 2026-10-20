"""Testes do cronometro de silencio da sessao.

Existe por causa de um defeito real, relatado pelos usuarios em 15/10/2026:
"trava em dois ou tres minutos, nao desconecta mas nao responde".

A causa era este cronometro. Ele media "tempo sem o usuario falar", e quem
escutava em silencio uma resposta longa era punido por isso. Nos dados reais,
10% das respostas do n8n passavam de 800 caracteres e a maior tinha 2781,
cerca de 3 minutos de fala continua. Com SESSION_SILENCE_TIMEOUT_S=90, a
sessao morria no meio da frase da IARA.

Zerar o cronometro no evento de mudanca de estado NAO resolve: o evento
dispara na transicao, e um discurso longo fica minutos sem transicao nenhuma.
Por isso o teste abaixo cobre justamente o caso longo.

    python tests/test_session_limits.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ok = 0
_falhas: list[str] = []


def checa(cond: bool, titulo: str) -> None:
    global _ok
    if cond:
        _ok += 1
        print(f"  ok      {titulo}")
    else:
        _falhas.append(titulo)
        print(f"  FALHOU  {titulo}")


class _CtxFalso:
    """Faz o papel do JobContext: so' precisa registrar o shutdown."""

    def __init__(self) -> None:
        self.encerrado_por: str | None = None

    def shutdown(self, reason: str = "") -> None:
        self.encerrado_por = reason


async def main() -> int:
    from agent.agent import SessionLimits

    print("=== silencio de verdade encerra a sessao ===")
    ctx = _CtxFalso()
    lim = SessionLimits(ctx, max_minutes=0, silence_timeout_s=2)
    lim.start()
    await asyncio.sleep(3.5)
    checa(lim.reason == "silencio", "2s de silencio real encerram")
    await lim.aclose()

    print("\n=== a IARA falando NAO conta como silencio ===")
    ctx = _CtxFalso()
    lim = SessionLimits(ctx, max_minutes=0, silence_timeout_s=2)
    lim.start()
    # Ela comeca a falar e passa muito tempo sem nenhuma outra transicao,
    # que e' exatamente o caso da resposta longa.
    lim.marcar_fala_do_agente(True)
    await asyncio.sleep(5)
    checa(lim.reason is None, "5s de fala continua nao encerram, com limite de 2s")
    checa(ctx.encerrado_por is None, "nao pediu shutdown durante a fala")

    # Ela cala. A partir dai o silencio volta a contar.
    lim.marcar_fala_do_agente(False)
    await asyncio.sleep(3.5)
    checa(lim.reason == "silencio", "depois que ela cala, o silencio volta a contar")
    await lim.aclose()

    print("\n=== fala do usuario zera o cronometro ===")
    ctx = _CtxFalso()
    lim = SessionLimits(ctx, max_minutes=0, silence_timeout_s=3)
    lim.start()
    for _ in range(4):
        await asyncio.sleep(1.2)
        lim.touch()
    checa(lim.reason is None, "toques periodicos seguram a sessao")
    await lim.aclose()

    print("\n=== tempo maximo encerra mesmo com conversa ativa ===")
    ctx = _CtxFalso()
    lim = SessionLimits(ctx, max_minutes=0, silence_timeout_s=0)
    lim._max_seconds = 2  # equivale a max_minutes pequeno demais para o construtor
    lim.start()
    lim.marcar_fala_do_agente(True)
    await asyncio.sleep(3.5)
    checa(lim.reason == "tempo_maximo", "o teto de tempo vence a fala em andamento")
    await lim.aclose()

    print("\n=== duracao informada para o acerto de minutos ===")
    ctx = _CtxFalso()
    lim = SessionLimits(ctx, max_minutes=20, silence_timeout_s=90)
    inicio = time.monotonic()
    await asyncio.sleep(1.1)
    m = lim.minutos_decorridos()
    checa(0.015 < m < 0.05, f"minutos_decorridos coerente ({m:.4f})")

    print()
    total = _ok + len(_falhas)
    if _falhas:
        print(f"{_ok}/{total} passaram. FALHAS:")
        for f in _falhas:
            print("  -", f)
        return 1
    print(f"{_ok}/{total} passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
