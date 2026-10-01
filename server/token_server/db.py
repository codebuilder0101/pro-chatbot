"""Conexao com o PostgreSQL e criacao do esquema.

O banco guarda **pessoas**, nao conversas. Nenhum conteudo do que a pessoa
falou com a IARA passa por aqui: isso e' dado sensivel de saude pela LGPD e
vive no fluxo do n8n, que e' do cliente. Aqui ficam so' identificacao e
credencial.

O esquema e' criado no boot, de forma idempotente. E' pequeno o bastante para
nao justificar uma ferramenta de migracao, e assim um deploy novo nao depende
de alguem lembrar de rodar um passo extra.
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

logger = logging.getLogger("iara.db")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id              BIGSERIAL PRIMARY KEY,
    email           TEXT        NOT NULL,
    nome            TEXT        NOT NULL DEFAULT '',
    senha_hash      TEXT        NOT NULL,
    -- empresa a que a pessoa pertence, pelo codigo usado no cadastro.
    codigo_acesso   TEXT,
    ativo           BOOLEAN     NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_acesso   TIMESTAMPTZ
);

-- Email e' a identidade. Indice unico sobre a forma normalizada para que
-- "Joao@Exemplo.com" e "joao@exemplo.com" nao virem duas contas.
CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_unico
    ON usuarios (lower(email));

CREATE TABLE IF NOT EXISTS sessoes (
    -- guardamos o hash do token, nunca o token: um vazamento de banco nao
    -- pode virar acesso imediato as contas.
    token_hash   TEXT        PRIMARY KEY,
    usuario_id   BIGINT      NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    criada_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em    TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS sessoes_usuario ON sessoes (usuario_id);
CREATE INDEX IF NOT EXISTS sessoes_expira ON sessoes (expira_em);
"""


class Banco:
    """Pool de conexoes. Uma instancia por processo."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    @property
    def configurado(self) -> bool:
        return bool(self._dsn)

    @property
    def ligado(self) -> bool:
        return self._pool is not None

    async def conectar(self) -> None:
        if self._pool is not None or not self._dsn:
            return
        # min_size baixo de proposito: este servico passa a maior parte do
        # tempo parado, e o Postgres aqui e' compartilhado com outros projetos.
        self._pool = await asyncpg.create_pool(
            self._dsn, min_size=1, max_size=5, command_timeout=10
        )
        async with self._pool.acquire() as con:
            await con.execute(_ESQUEMA)
        logger.info("banco conectado e esquema garantido")

    async def fechar(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _exigir(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("banco nao conectado")
        return self._pool

    async def buscar_um(self, sql: str, *args: Any) -> asyncpg.Record | None:
        async with self._exigir().acquire() as con:
            return await con.fetchrow(sql, *args)

    async def buscar(self, sql: str, *args: Any) -> list[asyncpg.Record]:
        async with self._exigir().acquire() as con:
            return list(await con.fetch(sql, *args))

    async def executar(self, sql: str, *args: Any) -> str:
        async with self._exigir().acquire() as con:
            return await con.execute(sql, *args)
