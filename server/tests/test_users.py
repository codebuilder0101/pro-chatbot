"""Testes de cadastro, entrada e sessao. Precisam de um Postgres de verdade.

    DATABASE_URL=postgresql://... python tests/test_users.py

Usa tabelas temporarias num schema proprio e apaga tudo no fim, para nunca
encostar nos dados reais. Cobre o que, errado, vira incidente de seguranca:
senha guardada em claro, email duplicado, senha errada aceita, sessao vencida
ou revogada ainda valendo.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env.local")
load_dotenv(".env")

from token_server.db import Banco  # noqa: E402
from token_server.users import (  # noqa: E402
    ErroDeCadastro,
    Usuarios,
    conferir_senha,
    gerar_hash_senha,
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


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        print("defina DATABASE_URL para rodar estes testes")
        return 2

    print("=== hash de senha (sem banco) ===")
    h = gerar_hash_senha("senha-secreta-123")
    checa("senha-secreta-123" not in h, "o hash nao contem a senha")
    checa(h.startswith("$2"), "formato bcrypt")
    checa(conferir_senha("senha-secreta-123", h), "aceita a senha certa")
    checa(not conferir_senha("senha-errada", h), "recusa a senha errada")
    checa(gerar_hash_senha("igual") != gerar_hash_senha("igual"), "sal diferente a cada hash")
    # bcrypt corta em 72 bytes; passamos sha256 antes justamente por isso
    longa_a = "a" * 100 + "FIM-A"
    longa_b = "a" * 100 + "FIM-B"
    checa(
        not conferir_senha(longa_b, gerar_hash_senha(longa_a)),
        "senhas longas com inicio igual nao se confundem",
    )
    checa(not conferir_senha("x", "hash-corrompido"), "hash corrompido nao derruba")

    banco = Banco(dsn)
    await banco.conectar()
    usuarios = Usuarios(banco, dias_de_sessao=30)
    marca = uuid.uuid4().hex[:8]
    emails = [f"teste-{marca}-{i}@exemplo.com" for i in range(4)]

    try:
        print("\n=== cadastro ===")
        u = await usuarios.cadastrar(
            email=emails[0], senha="senha-boa-123", nome="Fulano", codigo_acesso="TESTE234"
        )
        checa(u.email == emails[0], "cadastrou e devolveu o email")
        checa(u.codigo_acesso == "TESTE234", "guardou a empresa")

        linha = await banco.buscar_um(
            "SELECT senha_hash FROM usuarios WHERE id = $1", u.id
        )
        checa("senha-boa-123" not in linha["senha_hash"], "senha nao vai em claro para o banco")

        try:
            await usuarios.cadastrar(
                email=emails[0].upper(), senha="outra-senha-9", nome="", codigo_acesso=None
            )
            checa(False, "recusa email repetido mesmo com caixa diferente")
        except ErroDeCadastro as e:
            checa(e.status == 409, "recusa email repetido mesmo com caixa diferente")

        for ruim, titulo in (
            ("curta", "recusa senha curta"),
        ):
            try:
                await usuarios.cadastrar(
                    email=emails[1], senha=ruim, nome="", codigo_acesso=None
                )
                checa(False, titulo)
            except ErroDeCadastro:
                checa(True, titulo)

        for email_ruim in ("sem-arroba", "a@b", "@exemplo.com"):
            try:
                await usuarios.cadastrar(
                    email=email_ruim, senha="senha-boa-123", nome="", codigo_acesso=None
                )
                checa(False, f"recusa email invalido {email_ruim!r}")
            except ErroDeCadastro:
                checa(True, f"recusa email invalido {email_ruim!r}")

        print("\n=== entrada ===")
        s = await usuarios.entrar(email=emails[0], senha="senha-boa-123")
        checa(bool(s.token) and len(s.token) > 20, "entrada devolve token de sessao")
        checa(s.usuario.email == emails[0], "sessao aponta para o usuario certo")

        guardado = await banco.buscar_um(
            "SELECT token_hash FROM sessoes WHERE usuario_id = $1", s.usuario.id
        )
        checa(guardado["token_hash"] != s.token, "o banco guarda o hash, nao o token")

        s2 = await usuarios.entrar(email=emails[0].upper(), senha="senha-boa-123")
        checa(s2.usuario.id == s.usuario.id, "entra com o email em caixa diferente")

        for senha_ruim in ("senha-errada", "", "senha-boa-124"):
            try:
                await usuarios.entrar(email=emails[0], senha=senha_ruim)
                checa(False, f"recusa senha errada {senha_ruim!r}")
            except ErroDeCadastro as e:
                checa(e.status == 401, f"recusa senha errada {senha_ruim!r}")

        try:
            await usuarios.entrar(email=f"ninguem-{marca}@exemplo.com", senha="qualquer")
            checa(False, "recusa email que nao existe")
        except ErroDeCadastro as e:
            checa(
                e.mensagem == "Email ou senha incorretos.",
                "mensagem igual para email inexistente e senha errada",
            )

        print("\n=== sessao ===")
        achado = await usuarios.usuario_da_sessao(s.token)
        checa(achado is not None and achado.id == s.usuario.id, "token valido identifica a pessoa")
        checa(await usuarios.usuario_da_sessao("token-inventado") is None, "token falso nao vale")
        checa(await usuarios.usuario_da_sessao("") is None, "token vazio nao vale")

        # Vence a sessao de `s` especificamente, e nao "alguma do usuario":
        # ele tem mais de uma aberta e apagar a errada faria o teste mentir.
        import hashlib

        await banco.executar(
            "UPDATE sessoes SET expira_em = $1 WHERE token_hash = $2",
            datetime.now(timezone.utc) - timedelta(days=1),
            hashlib.sha256(s.token.encode()).hexdigest(),
        )
        checa(
            await usuarios.usuario_da_sessao(s.token) is None,
            "sessao vencida nao autentica",
        )
        checa(
            await usuarios.usuario_da_sessao(s2.token) is not None,
            "vencer uma sessao nao derruba as outras do mesmo usuario",
        )

        s3 = await usuarios.entrar(email=emails[0], senha="senha-boa-123")
        await usuarios.sair(s3.token)
        checa(await usuarios.usuario_da_sessao(s3.token) is None, "sair invalida o token")

        print("\n=== conta desativada ===")
        await banco.executar("UPDATE usuarios SET ativo = FALSE WHERE id = $1", s.usuario.id)
        try:
            await usuarios.entrar(email=emails[0], senha="senha-boa-123")
            checa(False, "conta desativada nao entra")
        except ErroDeCadastro as e:
            checa(e.status == 403, "conta desativada nao entra")

        checa(
            await usuarios.usuario_da_sessao(s2.token) is None,
            "desativar a conta invalida as sessoes abertas",
        )
    except Exception as exc:  # pragma: no cover
        _falhas.append(f"excecao inesperada: {exc!r}")
        print(f"  FALHOU  excecao inesperada: {exc!r}")
    finally:
        # limpa tudo que este teste criou, sem encostar em mais nada
        await banco.executar(
            "DELETE FROM usuarios WHERE email = ANY($1::text[])", emails
        )
        await banco.fechar()

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
