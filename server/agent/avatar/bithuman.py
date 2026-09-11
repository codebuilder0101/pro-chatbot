"""Motor de avatar bitHuman.

Dois modos, escolhidos pelo que voce configurar:

  nuvem  - BITHUMAN_AVATAR_ID preenchido. O bitHuman renderiza do lado dele.
           E' o que o "Agent code" do console habilita, e e' o nosso caso.
  local  - BITHUMAN_MODEL_PATH apontando para um .imx. O modelo roda dentro do
           processo do agente e consome CPU/RAM da maquina, em vez de ser
           cobrado por minuto remoto.

Sobre nomes: o que o console do bitHuman chama de **Agent code** e' o que o
plugin chama de `avatar_id`, e o que a API recebe como `agent_id`. Sao a mesma
coisa com tres nomes; conferido no codigo do plugin em 10/09/2026.

Restricao de plataforma, que nao aparece em lugar nenhum ate a instalacao
falhar: o pacote `bithuman` so' publica wheel para Linux x86_64, Linux aarch64
e macOS 14+ ARM. **Nao existe wheel para Windows** e ele nao compila da fonte.
Em Windows, so' dentro de WSL2 ou de um container Linux - que e' o que o
Dockerfile deste repositorio ja faz.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import AvatarEngine, AvatarEngineError, Health

logger = logging.getLogger("iara.avatar.bithuman")

_MODELS = ("essence", "expression")


class BitHumanAvatar(AvatarEngine):
    name = "bithuman"

    def __init__(self) -> None:
        self._api_secret = os.environ.get("BITHUMAN_API_SECRET", "").strip()
        self._avatar_id = os.environ.get("BITHUMAN_AVATAR_ID", "").strip()
        self._model_path = os.environ.get("BITHUMAN_MODEL_PATH", "").strip()
        self._model = os.environ.get("BITHUMAN_MODEL", "expression").strip()
        self._session: Any | None = None

        if self._model not in _MODELS:
            raise AvatarEngineError(
                f"BITHUMAN_MODEL invalido: {self._model!r}. Use essence ou expression."
            )

    async def start(self, session: Any, room: Any) -> None:
        if not self._api_secret:
            raise AvatarEngineError("BITHUMAN_API_KEY nao definido.")
        if not self._avatar_id and not self._model_path:
            raise AvatarEngineError("Defina BITHUMAN_AVATAR_ID ou BITHUMAN_MODEL_PATH.")

        try:
            from livekit.plugins import bithuman
        except ImportError as exc:  # pragma: no cover
            import platform

            detalhe = (
                " O bitHuman nao publica wheel para Windows: rode o agente em"
                " Linux, no WSL2, ou no container do Dockerfile."
                if platform.system() == "Windows"
                else " Instale: pip install livekit-plugins-bithuman"
            )
            raise AvatarEngineError("Plugin do bitHuman ausente." + detalhe) from exc

        kwargs: dict[str, Any] = {"model": self._model}
        if self._model_path:
            kwargs["model_path"] = self._model_path
        else:
            kwargs["avatar_id"] = self._avatar_id

        self._session = bithuman.AvatarSession(**kwargs)
        logger.info("iniciando avatar bithuman %s", kwargs)
        await self._session.start(session, room=room)

    async def aclose(self) -> None:
        if self._session is None:
            return
        try:
            closer = getattr(self._session, "aclose", None) or getattr(
                self._session, "stop", None
            )
            if closer is not None:
                await closer()
        except Exception:  # pragma: no cover
            logger.exception("falha ao encerrar avatar bithuman")
        finally:
            self._session = None

    async def health(self, deep: bool = False) -> Health:
        if not self._api_secret:
            return Health(False, self.name, "BITHUMAN_API_KEY ausente")
        if not self._avatar_id and not self._model_path:
            return Health(False, self.name, "avatar_id/model_path ausentes")
        if self._model_path and not os.path.exists(self._model_path):
            return Health(
                False, self.name, f"arquivo nao encontrado: {self._model_path}"
            )
        if deep:
            try:
                import livekit.plugins.bithuman  # noqa: F401
            except ImportError:
                return Health(
                    False, self.name, "livekit-plugins-bithuman nao instalado"
                )
        return Health(True, self.name, f"model={self._model}")
