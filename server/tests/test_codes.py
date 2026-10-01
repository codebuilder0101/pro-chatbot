"""Testes do registro de codigos de acesso. Rodam sem rede e sem servidor.

    python tests/test_codes.py

Cobrem o que custa dinheiro se estiver errado: teto de minutos, reserva,
acerto no fim, idempotencia e revogacao.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from token_server.codes import (  # noqa: E402
    CodigoInvalido,
    RegistroDeCodigos,
    gerar,
    normalizar,
)

_ok = 0
_falhas: list[str] = []


def checa(condicao: bool, titulo: str) -> None:
    global _ok
    if condicao:
        _ok += 1
        print(f"  ok      {titulo}")
    else:
        _falhas.append(titulo)
        print(f"  FALHOU  {titulo}")


async def cenario(nome: str):
    tmp = Path(tempfile.mkdtemp()) / "codes.json"
    print(f"\n--- {nome} ---")
    return RegistroDeCodigos(tmp)


async def main() -> int:
    print("=== normalizacao e geracao ===")
    checa(normalizar("abcd-1234") == "ABCD1234", "tira hifen e sobe a caixa")
    checa(normalizar("  ab cd 12 34 ") == "ABCD1234", "tira espacos")
    checa(normalizar("") == "", "vazio continua vazio")
    codigo = gerar()
    checa(len(codigo) == 8, "codigo gerado tem 8 caracteres")
    checa(not set(codigo) & set("O0I1L"), "codigo gerado evita caracteres ambiguos")

    r = await cenario("criacao e listagem")
    novo = await r.criar("Clinica A", teto_minutos=60)
    checa(len(novo["codigo"]) == 8, "criou com codigo gerado")
    lista = await r.listar()
    checa(len(lista) == 1 and lista[0]["empresa"] == "Clinica A", "aparece na listagem")
    try:
        await r.criar("Outra", codigo=novo["codigo"])
        checa(False, "recusa codigo duplicado")
    except CodigoInvalido:
        checa(True, "recusa codigo duplicado")

    r = await cenario("autorizacao basica")
    c = (await r.criar("Clinica B", codigo="TESTE123", teto_minutos=60))["codigo"]
    auth = await r.autorizar("teste-123", "sala1", 20)
    checa(auth.codigo == "TESTE123", "aceita o codigo com hifen e minuscula")
    checa(auth.empresa == "Clinica B", "devolve a empresa")
    lista = await r.listar()
    checa(lista[0]["minutos_reservados"] == 20, "reservou 20 minutos")
    checa(lista[0]["minutos_usados"] == 0, "ainda nao cobrou nada")
    checa(lista[0]["sessoes"] == 1, "contou a sessao")

    print("\n--- acerto no fim da sessao ---")
    await r.encerrar("sala1", 7.4)
    lista = await r.listar()
    checa(lista[0]["minutos_reservados"] == 0, "devolveu a reserva")
    checa(lista[0]["minutos_usados"] == 7, "cobrou os minutos reais arredondados")

    print("\n--- idempotencia ---")
    await r.encerrar("sala1", 7.4)
    lista = await r.listar()
    checa(lista[0]["minutos_usados"] == 7, "encerrar duas vezes nao cobra de novo")
    checa(await r.encerrar("sala-que-nunca-existiu", 5) is None, "sala desconhecida nao quebra")

    r = await cenario("teto de minutos")
    await r.criar("Clinica C", codigo="TETO0000", teto_minutos=40)
    await r.autorizar("TETO0000", "s1", 20)
    await r.autorizar("TETO0000", "s2", 20)
    try:
        await r.autorizar("TETO0000", "s3", 20)
        checa(False, "recusa quando a reserva estoura o teto")
    except CodigoInvalido as e:
        checa("teto" in e.motivo, "recusa quando a reserva estoura o teto")
    # Acertar s1 em 2 minutos libera 18 do teto, mas s2 continua aberta com
    # 20 reservados. Sobram 18 e a proxima sessao pode usar 20, entao recusar
    # e' o certo: a reserva existe justamente para nao estourar o teto se a
    # sessao aberta for ate o fim.
    await r.encerrar("s1", 2)
    try:
        await r.autorizar("TETO0000", "s4", 20)
        checa(False, "com sessao aberta, nao libera vaga que nao cabe")
    except CodigoInvalido:
        checa(True, "com sessao aberta, nao libera vaga que nao cabe")

    # Fechando s2 tambem, sobra 40 - 2 - 2 = 36 e a nova sessao cabe.
    await r.encerrar("s2", 2)
    auth = await r.autorizar("TETO0000", "s5", 20)
    checa(auth.codigo == "TETO0000", "depois de fechar tudo, cabe nova sessao")

    print("\n--- nunca cobra mais do que reservou ---")
    r2 = await cenario("cobranca limitada a reserva")
    await r2.criar("Clinica D", codigo="LIMITE00", teto_minutos=100)
    await r2.autorizar("LIMITE00", "x1", 20)
    await r2.encerrar("x1", 999)
    lista = await r2.listar()
    checa(lista[0]["minutos_usados"] == 20, "duracao absurda e' limitada a reserva")

    r = await cenario("validade e revogacao")
    ontem = (date.today() - timedelta(days=1)).isoformat()
    amanha = (date.today() + timedelta(days=1)).isoformat()
    await r.criar("Vencido", codigo="VENCIDO0", validade=ontem)
    await r.criar("Valido", codigo="VALIDO00", validade=amanha)
    try:
        await r.autorizar("VENCIDO0", "s1", 20)
        checa(False, "recusa codigo vencido")
    except CodigoInvalido as e:
        checa("vencido" in e.motivo, "recusa codigo vencido")
    auth = await r.autorizar("VALIDO00", "s2", 20)
    checa(auth.codigo == "VALIDO00", "aceita codigo dentro da validade")

    await r.alterar("VALIDO00", ativo=False)
    try:
        await r.autorizar("VALIDO00", "s3", 20)
        checa(False, "recusa codigo desativado")
    except CodigoInvalido as e:
        checa("desativado" in e.motivo, "recusa codigo desativado")

    await r.remover("VALIDO00")
    try:
        await r.autorizar("VALIDO00", "s4", 20)
        checa(False, "recusa codigo removido")
    except CodigoInvalido as e:
        checa("desconhecido" in e.motivo, "recusa codigo removido")

    r = await cenario("entradas invalidas")
    for ruim in ("", "   ", "---", "nao-existe"):
        try:
            await r.autorizar(ruim, "s", 20)
            checa(False, f"recusa entrada invalida {ruim!r}")
        except CodigoInvalido:
            checa(True, f"recusa entrada invalida {ruim!r}")

    r = await cenario("sem teto definido")
    await r.criar("Ilimitada", codigo="SEMTETO0")
    for i in range(5):
        await r.autorizar("SEMTETO0", f"s{i}", 20)
    lista = await r.listar()
    checa(lista[0]["minutos_reservados"] == 100, "sem teto nao bloqueia")

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
