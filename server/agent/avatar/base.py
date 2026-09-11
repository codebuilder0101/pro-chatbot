"""Interface minima de um motor de avatar.

Regra do projeto: nenhum modulo fora deste pacote importa heygen.py ou
bithuman.py. Quem precisa de um avatar chama factory.create_avatar_engine().
Trocar de fornecedor e mudar AVATAR_ENGINE no .env, nunca refatorar.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Health:
    ok: bool
    engine: str
    detail: str = ""


class AvatarEngineError(RuntimeError):
    """Falha de configuracao ou de inicializacao de um motor de avatar."""


class AvatarEngine(abc.ABC):
    """Contrato que HeyGen e bitHuman implementam de forma intercambiavel."""

    #: identificador curto usado em logs e metricas
    name: str = "base"

    @property
    def publishes_room_audio(self) -> bool:
        """True quando o motor publica o audio junto com o video.

        Nesse caso a AgentSession nao pode publicar o proprio audio na sala,
        senao o usuario ouve a voz duas vezes, dessincronizada.
        """
        return True

    @abc.abstractmethod
    async def start(self, session: Any, room: Any) -> None:
        """Entra na sala e comeca a publicar a faixa de video do avatar."""

    @abc.abstractmethod
    async def aclose(self) -> None:
        """Encerra a renderizacao e libera o recurso cobrado por minuto."""

    @abc.abstractmethod
    async def health(self, deep: bool = False) -> Health:
        """Checagem de prontidao do motor.

        Com `deep=False` (padrao) olha apenas a configuracao: chaves e ids
        presentes, arquivo de modelo existente. Nao importa nada.

        Com `deep=True` tambem confirma que o plugin esta instalado, o que
        exige importar o SDK inteiro. Isso e' caro e, pior, nao e' seguro em
        qualquer processo: um binario nativo incompativel com a CPU derruba o
        processo com segfault, que nenhum try/except pega. Por isso o token
        server usa a checagem rasa - um problema no avatar nao pode derrubar
        a emissao de tokens.
        """

    def __repr__(self) -> str:  # pragma: no cover - conveniencia de log
        return f"<AvatarEngine {self.name}>"
