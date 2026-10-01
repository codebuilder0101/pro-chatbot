"""Códigos de acesso: quem pode abrir conversa, e por quantos minutos.

Por que isto existe
-------------------
Um APK é descompilável. A chave que o app carrega no header `x-api-key` pode
ser extraída por qualquer pessoa com o arquivo em mãos, e foi exatamente isso
que aconteceu num teste nosso. Enquanto ela era o único controle, quem tivesse
o APK abria sessão de avatar à vontade, e cada minuto de avatar é pago.

O código de acesso resolve isso sem exigir cadastro, e-mail ou senha: o
segredo que autoriza a conversa **não** mora dentro do app. Ele é digitado
pela pessoa, fica guardado no aparelho dela, e pode ser revogado no servidor
sem republicar o APK.

Como os minutos são contados
----------------------------
O token server não fica sabendo quando a conversa termina, então contar o
tempo "depois" seria furado: bastaria nunca avisar o fim para gastar infinito.
Por isso o controle é por **reserva**:

  1. ao emitir o token, debita o pior caso (SESSION_MAX_MINUTES) do saldo;
  2. quando o agente encerra, ele informa a duração real e a diferença volta.

Se o agente morrer e nunca informar, o pior caso continua debitado. Isso erra
para o lado seguro, que é o único lado aceitável quando o erro custa dinheiro.

O arquivo é a fonte da verdade, gravado de forma atômica. Um único processo
uvicorn escreve nele, serializado por um lock.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import string
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("iara.codes")

#: Alfabeto sem os caracteres que a pessoa erra ao ouvir pelo telefone:
#: O/0, I/1, L. Vale a pena: o código é ditado por voz na prática.
_ALFABETO = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1L")

_TAMANHO_PADRAO = 8
_LIMPA = re.compile(r"[^A-Za-z0-9]")


def normalizar(codigo: str) -> str:
    """Tira espaços, hífens e caixa. "abcd-1234" e "ABCD 1234" viram o mesmo."""
    return _LIMPA.sub("", codigo or "").upper()


def gerar(tamanho: int = _TAMANHO_PADRAO) -> str:
    return "".join(secrets.choice(_ALFABETO) for _ in range(tamanho))


class CodigoInvalido(Exception):
    """Código recusado. `motivo` é curto e serve para log, não para o usuário."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class Autorizacao:
    codigo: str
    empresa: str
    minutos_reservados: int


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RegistroDeCodigos:
    """Lê e grava o arquivo de códigos. Uma instância por processo."""

    def __init__(self, caminho: str | os.PathLike[str]) -> None:
        self._caminho = Path(caminho)
        self._lock = asyncio.Lock()

    # -- leitura ---------------------------------------------------------

    def _ler(self) -> dict[str, Any]:
        if not self._caminho.exists():
            return {"codigos": {}, "sessoes": {}}
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception("arquivo de codigos ilegivel: %s", self._caminho)
            raise
        dados.setdefault("codigos", {})
        dados.setdefault("sessoes", {})
        return dados

    def _gravar(self, dados: dict[str, Any]) -> None:
        """Grava atômico: escreve ao lado e troca. Nunca deixa arquivo pela metade."""
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._caminho.with_suffix(self._caminho.suffix + ".tmp")
        tmp.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, self._caminho)
        try:
            self._caminho.chmod(0o600)
        except OSError:  # pragma: no cover - sistema de arquivos sem suporte
            pass

    # -- consulta --------------------------------------------------------

    async def listar(self) -> list[dict[str, Any]]:
        async with self._lock:
            dados = self._ler()
        saida = []
        for codigo, c in sorted(dados["codigos"].items()):
            saida.append(
                {
                    "codigo": codigo,
                    "empresa": c.get("empresa", ""),
                    "ativo": bool(c.get("ativo", True)),
                    "validade": c.get("validade"),
                    "teto_minutos": c.get("teto_minutos"),
                    "minutos_usados": c.get("minutos_usados", 0),
                    "minutos_reservados": c.get("minutos_reservados", 0),
                    "sessoes": c.get("sessoes", 0),
                    "criado_em": c.get("criado_em"),
                    "ultimo_uso": c.get("ultimo_uso"),
                }
            )
        return saida

    # -- escrita ---------------------------------------------------------

    async def criar(
        self,
        empresa: str,
        *,
        codigo: str | None = None,
        validade: str | None = None,
        teto_minutos: int | None = None,
    ) -> dict[str, Any]:
        codigo = normalizar(codigo) if codigo else gerar()
        if len(codigo) < 4:
            raise CodigoInvalido("codigo curto demais")
        if validade:
            # levanta ValueError se a data nao for AAAA-MM-DD
            date.fromisoformat(validade)

        async with self._lock:
            dados = self._ler()
            if codigo in dados["codigos"]:
                raise CodigoInvalido("codigo ja existe")
            dados["codigos"][codigo] = {
                "empresa": empresa,
                "ativo": True,
                "validade": validade,
                "teto_minutos": teto_minutos,
                "minutos_usados": 0,
                "minutos_reservados": 0,
                "sessoes": 0,
                "criado_em": _agora(),
                "ultimo_uso": None,
            }
            self._gravar(dados)
        logger.info("codigo criado empresa=%r teto=%s", empresa, teto_minutos)
        return {"codigo": codigo, "empresa": empresa}

    async def alterar(self, codigo: str, **campos: Any) -> dict[str, Any]:
        codigo = normalizar(codigo)
        permitidos = {"empresa", "ativo", "validade", "teto_minutos"}
        async with self._lock:
            dados = self._ler()
            c = dados["codigos"].get(codigo)
            if c is None:
                raise CodigoInvalido("codigo nao existe")
            for k, v in campos.items():
                if k in permitidos and v is not None:
                    if k == "validade":
                        date.fromisoformat(v)
                    c[k] = v
            self._gravar(dados)
        logger.info("codigo alterado codigo=%s campos=%s", codigo, sorted(campos))
        return {"codigo": codigo, **{k: v for k, v in campos.items() if v is not None}}

    async def remover(self, codigo: str) -> None:
        codigo = normalizar(codigo)
        async with self._lock:
            dados = self._ler()
            if dados["codigos"].pop(codigo, None) is None:
                raise CodigoInvalido("codigo nao existe")
            self._gravar(dados)
        logger.info("codigo removido codigo=%s", codigo)

    # -- uso -------------------------------------------------------------

    async def validar(self, codigo_bruto: str) -> str:
        """Confere o código sem reservar nada. Usado no cadastro.

        Cadastrar não abre conversa, então não pode gastar minuto nem contar
        sessão. Só responde "este código serve?" e devolve a forma normalizada.
        """
        codigo = normalizar(codigo_bruto)
        if not codigo:
            raise CodigoInvalido("codigo vazio")

        async with self._lock:
            dados = self._ler()
            c = dados["codigos"].get(codigo)

        if c is None:
            raise CodigoInvalido("codigo desconhecido")
        if not c.get("ativo", True):
            raise CodigoInvalido("codigo desativado")
        validade = c.get("validade")
        if validade and date.fromisoformat(validade) < datetime.now(timezone.utc).date():
            raise CodigoInvalido("codigo vencido")
        return codigo

    async def autorizar(self, codigo_bruto: str, sala: str, minutos: int) -> Autorizacao:
        """Valida o código e reserva `minutos`. Levanta CodigoInvalido se não puder."""
        codigo = normalizar(codigo_bruto)
        if not codigo:
            raise CodigoInvalido("codigo vazio")

        async with self._lock:
            dados = self._ler()
            c = dados["codigos"].get(codigo)
            if c is None:
                raise CodigoInvalido("codigo desconhecido")
            if not c.get("ativo", True):
                raise CodigoInvalido("codigo desativado")

            validade = c.get("validade")
            if validade and date.fromisoformat(validade) < datetime.now(timezone.utc).date():
                raise CodigoInvalido("codigo vencido")

            teto = c.get("teto_minutos")
            if teto is not None:
                comprometido = c.get("minutos_usados", 0) + c.get("minutos_reservados", 0)
                if comprometido + minutos > teto:
                    raise CodigoInvalido("teto de minutos atingido")

            c["minutos_reservados"] = c.get("minutos_reservados", 0) + minutos
            c["sessoes"] = c.get("sessoes", 0) + 1
            c["ultimo_uso"] = _agora()
            # a sala guarda a reserva para o acerto no fim
            dados["sessoes"][sala] = {
                "codigo": codigo,
                "reservado": minutos,
                "aberta_em": _agora(),
            }
            self._gravar(dados)

        return Autorizacao(codigo=codigo, empresa=c.get("empresa", ""), minutos_reservados=minutos)

    async def encerrar(self, sala: str, minutos_reais: float) -> dict[str, Any] | None:
        """Acerta a reserva com a duração real. Idempotente por sala."""
        async with self._lock:
            dados = self._ler()
            sessao = dados["sessoes"].pop(sala, None)
            if sessao is None:
                # já acertada, ou sala que nunca passou por aqui
                return None

            codigo = sessao["codigo"]
            reservado = int(sessao.get("reservado", 0))
            c = dados["codigos"].get(codigo)
            if c is None:
                self._gravar(dados)
                return None

            # nunca cobrar mais do que foi reservado: o teto da sessão já é o
            # SESSION_MAX_MINUTES e o agente encerra sozinho ao atingi-lo.
            reais = max(0, min(int(round(minutos_reais)), reservado))
            c["minutos_reservados"] = max(0, c.get("minutos_reservados", 0) - reservado)
            c["minutos_usados"] = c.get("minutos_usados", 0) + reais
            self._gravar(dados)

        logger.info(
            "sessao encerrada sala=%s codigo=%s reservado=%smin real=%smin",
            sala, codigo, reservado, reais,
        )
        return {"codigo": codigo, "reservado": reservado, "cobrado": reais}
