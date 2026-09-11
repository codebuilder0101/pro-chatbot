"""Unico ponto do projeto autorizado a importar um motor concreto.

Se voce estiver prestes a escrever `from .heygen import ...` em qualquer outro
arquivo, pare: acrescente aqui em vez disso.
"""

from __future__ import annotations

from ..config import settings
from .base import AvatarEngine, AvatarEngineError

ENGINES = ("heygen", "bithuman")


def create_avatar_engine(name: str | None = None) -> AvatarEngine:
    engine = (name or settings.avatar_engine or "").lower().strip()

    if engine == "heygen":
        from .heygen import HeyGenAvatar

        return HeyGenAvatar()

    if engine == "bithuman":
        from .bithuman import BitHumanAvatar

        return BitHumanAvatar()

    raise AvatarEngineError(
        f"AVATAR_ENGINE invalido: {engine!r}. Valores aceitos: {', '.join(ENGINES)}."
    )
