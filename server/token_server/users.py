"""Cadastro, entrada e sessao das pessoas.

Decisoes que valem explicacao
-----------------------------
**A senha nunca e' guardada.** Guardamos um hash bcrypt, que e' lento de
proposito: quem roubar o banco nao sai testando senha em massa. bcrypt tem
limite de 72 bytes na entrada, entao a senha passa antes por SHA-256 e o
digest e' que vai para o bcrypt. Sem isso, duas senhas longas que compartilham
os primeiros 72 bytes abririam a mesma conta.

**O cadastro exige codigo de acesso.** Sem isso, qualquer pessoa criaria conta
e voltariamos ao problema que o codigo veio resolver: minuto de avatar e' pago,
e quem paga e' o cliente. O codigo diz de qual empresa a pessoa e'.

**A sessao e' um token opaco, guardado em hash.** Nao e' JWT: queremos poder
revogar na hora, e o banco ja esta aqui. O que vai para o aparelho e' o token
em claro; o que fica no banco e' o SHA-256 dele. Vazar o banco nao da acesso.

**Mensagem de erro unica na entrada.** Dizer "email nao existe" em vez de
"senha errada" entrega quais emails estao cadastrados.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt

from .db import Banco

logger = logging.getLogger("iara.users")

#: Simples de proposito. Validar email por regex a fundo e' ilusao: quem
#: confirma que o endereco existe e' um e-mail de verificacao, que esta fora
#: do escopo desta fase. Isto so' barra digitacao obviamente errada.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SENHA_MINIMA = 8


class ErroDeCadastro(Exception):
    """Falha esperada de cadastro ou entrada. A mensagem vai para o usuario."""

    def __init__(self, mensagem: str, *, status: int = 400) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


@dataclass(frozen=True)
class Usuario:
    id: int
    email: str
    nome: str
    codigo_acesso: str | None


@dataclass(frozen=True)
class Sessao:
    token: str
    usuario: Usuario
    expira_em: datetime


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def gerar_hash_senha(senha: str) -> str:
    # SHA-256 antes do bcrypt por causa do limite de 72 bytes. Ver o cabecalho.
    digest = hashlib.sha256(senha.encode("utf-8")).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")


def conferir_senha(senha: str, hash_guardado: str) -> bool:
    digest = hashlib.sha256(senha.encode("utf-8")).digest()
    try:
        return bcrypt.checkpw(digest, hash_guardado.encode("utf-8"))
    except (ValueError, TypeError):  # hash corrompido no banco
        return False


def validar_senha(senha: str) -> None:
    if len(senha or "") < SENHA_MINIMA:
        raise ErroDeCadastro(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")


def validar_email(email: str) -> str:
    email = normalizar_email(email)
    if not _EMAIL.match(email):
        raise ErroDeCadastro("Email invalido.")
    if len(email) > 254:
        raise ErroDeCadastro("Email longo demais.")
    return email


class Usuarios:
    """Operacoes de conta. Toda a persistencia passa por aqui."""

    def __init__(self, banco: Banco, *, dias_de_sessao: int = 30) -> None:
        self._banco = banco
        self._dias = dias_de_sessao

    # -- cadastro --------------------------------------------------------

    async def cadastrar(
        self, *, email: str, senha: str, nome: str, codigo_acesso: str | None
    ) -> Usuario:
        email = validar_email(email)
        validar_senha(senha)
        nome = (nome or "").strip()[:120]

        linha = await self._banco.buscar_um(
            """
            INSERT INTO usuarios (email, nome, senha_hash, codigo_acesso)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (lower(email)) DO NOTHING
            RETURNING id, email, nome, codigo_acesso
            """,
            email, nome, gerar_hash_senha(senha), codigo_acesso,
        )
        if linha is None:
            # ON CONFLICT ... DO NOTHING devolve vazio quando o email ja existe.
            # Nao vazamos mais do que a pessoa ja sabe ao tentar se cadastrar.
            raise ErroDeCadastro("Ja existe uma conta com esse email.", status=409)

        logger.info("conta criada id=%s empresa=%s", linha["id"], codigo_acesso)
        return Usuario(
            id=linha["id"],
            email=linha["email"],
            nome=linha["nome"],
            codigo_acesso=linha["codigo_acesso"],
        )

    # -- entrada ---------------------------------------------------------

    async def entrar(self, *, email: str, senha: str) -> Sessao:
        email = normalizar_email(email)
        linha = await self._banco.buscar_um(
            """
            SELECT id, email, nome, senha_hash, codigo_acesso, ativo
            FROM usuarios WHERE lower(email) = $1
            """,
            email,
        )

        # Confere a senha mesmo quando o email nao existe, contra um hash
        # descartavel. Sem isso, a diferenca de tempo entre "email existe" e
        # "nao existe" entrega quais emails estao cadastrados.
        hash_guardado = linha["senha_hash"] if linha else _HASH_FALSO
        senha_ok = conferir_senha(senha, hash_guardado)

        if linha is None or not senha_ok:
            raise ErroDeCadastro("Email ou senha incorretos.", status=401)
        if not linha["ativo"]:
            raise ErroDeCadastro("Esta conta esta desativada.", status=403)

        usuario = Usuario(
            id=linha["id"],
            email=linha["email"],
            nome=linha["nome"],
            codigo_acesso=linha["codigo_acesso"],
        )
        return await self._abrir_sessao(usuario)

    async def _abrir_sessao(self, usuario: Usuario) -> Sessao:
        token = secrets.token_urlsafe(32)
        expira = datetime.now(timezone.utc) + timedelta(days=self._dias)
        await self._banco.executar(
            "INSERT INTO sessoes (token_hash, usuario_id, expira_em) VALUES ($1, $2, $3)",
            _hash_token(token), usuario.id, expira,
        )
        await self._banco.executar(
            "UPDATE usuarios SET ultimo_acesso = now() WHERE id = $1", usuario.id
        )
        # Faxina barata: aproveita a entrada para limpar sessoes vencidas, em
        # vez de exigir uma tarefa agendada so' para isso.
        await self._banco.executar("DELETE FROM sessoes WHERE expira_em < now()")
        return Sessao(token=token, usuario=usuario, expira_em=expira)

    # -- sessao ----------------------------------------------------------

    async def usuario_da_sessao(self, token: str) -> Usuario | None:
        if not token:
            return None
        linha = await self._banco.buscar_um(
            """
            SELECT u.id, u.email, u.nome, u.codigo_acesso
            FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id
            WHERE s.token_hash = $1 AND s.expira_em > now() AND u.ativo
            """,
            _hash_token(token),
        )
        if linha is None:
            return None
        return Usuario(
            id=linha["id"],
            email=linha["email"],
            nome=linha["nome"],
            codigo_acesso=linha["codigo_acesso"],
        )

    async def sair(self, token: str) -> None:
        if token:
            await self._banco.executar(
                "DELETE FROM sessoes WHERE token_hash = $1", _hash_token(token)
            )


#: Hash de uma senha que ninguem usa, so' para gastar o mesmo tempo quando o
#: email nao existe. Calculado uma vez no import.
_HASH_FALSO = gerar_hash_senha(secrets.token_urlsafe(16))
