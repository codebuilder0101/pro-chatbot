"""Cliente do webhook do n8n.

Nesta arquitetura o n8n nao e' porteiro, e' o cerebro. Toda a logica clinica
da IARA vive la, ja montada e validada. O agente aqui vira encanamento: ouve,
transcreve, entrega o texto ao n8n, recebe a resposta pronta e passa para a
voz e para o avatar.

Consequencia direta e inevitavel: a resposta chega inteira, nao em streaming.
Um fluxo clinico com muitas condicoes leva segundos, e nesse intervalo o avatar
ficaria parado encarando o usuario. Quem resolve isso e' o enchimento de espera
(ver pipeline.py), nao este modulo. Aqui a unica obrigacao e' ser rapido,
cancelavel e nunca deixar a sessao pendurada.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .config import settings

logger = logging.getLogger("iara.n8n")

#: Chaves aceitas na resposta, em ordem de preferencia. O n8n devolve coisas
#: diferentes conforme o no' final usado (Respond to Webhook, Set, AI Agent),
#: e nao vale a pena obrigar o cliente a mudar o workflow por causa disso.
_REPLY_KEYS = ("reply", "text", "output", "message", "answer", "response", "content")


class BrainError(RuntimeError):
    """O n8n nao respondeu, respondeu erro, ou respondeu algo inutilizavel."""


@dataclass
class BrainReply:
    text: str
    latency_ms: float
    end_session: bool = False
    raw: Any = None


@dataclass
class _Turn:
    role: str
    content: str


class N8nBrain:
    """Uma instancia por sessao. Guarda o historico e fala com o webhook.

    O historico e' mantido aqui, e nao lido do ChatContext da sessao, de
    proposito: o ChatContext contem tambem as frases de espera ("deixa eu ver
    aqui"), que sao artificio de UX e nao fazem parte da conversa clinica.
    Mandar isso de volta para o n8n sujaria a memoria do fluxo.
    """

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str = "",
        webhook_url: str | None = None,
    ) -> None:
        self._session_id = session_id
        self._user_id = user_id
        self._url = (webhook_url or settings.n8n_webhook_url).strip()
        self._turn = 0
        self._history: list[_Turn] = []
        self._own_http: aiohttp.ClientSession | None = None

        if not self._url:
            raise BrainError("N8N_WEBHOOK_URL nao definido.")

    # -- http ----------------------------------------------------------

    def _http(self) -> aiohttp.ClientSession:
        """Reaproveita a sessao HTTP do framework quando existe.

        Fora de um job (testes, scripts) ela nao existe, entao abrimos uma
        propria e fechamos em aclose().
        """
        try:
            from livekit.agents import utils

            return utils.http_context.http_session()
        except Exception:
            if self._own_http is None or self._own_http.closed:
                self._own_http = aiohttp.ClientSession()
            return self._own_http

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if settings.n8n_auth_token:
            headers[settings.n8n_auth_header] = settings.n8n_auth_token
        return headers

    # -- chamada -------------------------------------------------------

    async def ask(self, text: str) -> BrainReply:
        """Manda uma fala do usuario e devolve a resposta do fluxo clinico.

        Cancelavel: se o usuario interromper, a task e' cancelada e a
        requisicao morre junto, sem deixar o n8n respondendo para ninguem.
        """
        self._turn += 1
        payload = {
            "session_id": self._session_id,
            "room": self._session_id,
            "user_id": self._user_id,
            "turn": self._turn,
            "locale": settings.stt_language,
            "text": text,
            "history": [
                {"role": t.role, "content": t.content}
                for t in self._history[-settings.n8n_history_turns :]
            ]
            if settings.n8n_history_turns > 0
            else [],
        }

        started = time.monotonic()
        last_error: Exception | None = None

        # Uma repeticao, e so' para falha de conexao ou 5xx. Timeout nao se
        # repete: dobrar a espera de um fluxo que ja demorou demais e' punir
        # o usuario duas vezes.
        for attempt in range(2):
            try:
                body, content_type = await self._post(payload)
                reply_text, end_session, raw = _parse_reply(body, content_type)
                latency_ms = round((time.monotonic() - started) * 1000.0, 1)

                self._history.append(_Turn("user", text))
                self._history.append(_Turn("assistant", reply_text))

                logger.info(
                    "n8n turno=%d latencia=%.0fms chars=%d",
                    self._turn,
                    latency_ms,
                    len(reply_text),
                )
                return BrainReply(
                    text=reply_text,
                    latency_ms=latency_ms,
                    end_session=end_session,
                    raw=raw,
                )

            except asyncio.CancelledError:
                raise
            except _Retryable as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning("n8n falhou (%s), repetindo uma vez", exc)
                    continue
            except BrainError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                break

        raise BrainError(f"n8n indisponivel: {last_error}")

    async def _post(self, payload: dict[str, Any]) -> tuple[Any, str]:
        timeout = aiohttp.ClientTimeout(total=settings.n8n_timeout_s)
        try:
            async with self._http().post(
                self._url,
                json=payload,
                headers=self._headers(),
                timeout=timeout,
            ) as resp:
                content_type = (resp.headers.get("content-type") or "").lower()
                text = await resp.text()

                if resp.status >= 500:
                    raise _Retryable(f"HTTP {resp.status}")
                if resp.status >= 400:
                    raise BrainError(f"HTTP {resp.status}: {text[:200]}")

                if "json" in content_type:
                    import json

                    try:
                        return json.loads(text), content_type
                    except ValueError as exc:
                        raise BrainError(f"JSON invalido do n8n: {exc}") from exc
                return text, content_type

        except asyncio.TimeoutError as exc:
            raise BrainError(
                f"n8n nao respondeu em {settings.n8n_timeout_s}s"
            ) from exc
        except aiohttp.ClientError as exc:
            raise _Retryable(str(exc)) from exc

    async def aclose(self) -> None:
        if self._own_http is not None and not self._own_http.closed:
            await self._own_http.close()
        self._own_http = None


class _Retryable(Exception):
    """Falha transitoria: vale uma segunda tentativa."""


def _parse_reply(body: Any, content_type: str) -> tuple[str, bool, Any]:
    """Extrai o texto da resposta, aceitando os formatos que o n8n costuma dar.

    Tolerante de proposito. O workflow do cliente ja existe e foi validado
    clinicamente; obriga-lo a mudar o no' final so' para casar com um formato
    nosso seria trocar risco de integracao por capricho.
    """
    raw = body

    # corpo em texto puro
    if isinstance(body, str) and "json" not in content_type:
        text = body.strip()
        if not text:
            raise BrainError("n8n respondeu vazio")
        return text, False, raw

    # o no' "Respond to Webhook" costuma devolver uma lista de itens
    if isinstance(body, list):
        if not body:
            raise BrainError("n8n respondeu uma lista vazia")
        body = body[0]

    if isinstance(body, str):
        text = body.strip()
        if not text:
            raise BrainError("n8n respondeu vazio")
        return text, False, raw

    if not isinstance(body, dict):
        raise BrainError(f"formato inesperado do n8n: {type(body).__name__}")

    # o AI Agent do n8n aninha em "json". Desaninha antes de ler qualquer
    # chave, senao um end_session que venha la dentro passa despercebido.
    if "json" in body and isinstance(body["json"], dict):
        body = {**body["json"], **{k: v for k, v in body.items() if k != "json"}}

    end_session = bool(body.get("end_session") or body.get("endSession"))

    for key in _REPLY_KEYS:
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), end_session, raw
        # um nivel de aninhamento: {"output": {"text": "..."}}
        if isinstance(value, dict):
            for inner in _REPLY_KEYS:
                nested = value.get(inner)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip(), end_session, raw

    raise BrainError(
        "n8n respondeu sem texto. Chaves aceitas: " + ", ".join(_REPLY_KEYS)
    )
