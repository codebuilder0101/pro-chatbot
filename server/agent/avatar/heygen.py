"""Motor de avatar HeyGen.

Nota de nomenclatura, importante para quem for dar manutencao:
o produto que a especificacao chama de "HeyGen Interactive Avatar" foi
renomeado para "HeyGen LiveAvatar", e o plugin oficial do LiveKit se chama
`livekit-plugins-liveavatar`. Nao existe plugin chamado "heygen".
O arquivo mantem o nome heygen.py porque e assim que o cliente chama o produto.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import AvatarEngine, AvatarEngineError, Health

logger = logging.getLogger("iara.avatar.heygen")

_QUALITIES = ("very_high", "high", "medium", "low")


class HeyGenAvatar(AvatarEngine):
    name = "heygen"

    def __init__(self) -> None:
        self._avatar_id = os.environ.get("HEYGEN_AVATAR_ID", "").strip()
        self._api_key = os.environ.get("LIVEAVATAR_API_KEY", "").strip()
        self._quality = os.environ.get("HEYGEN_VIDEO_QUALITY", "high").strip() or "high"
        self._session: Any | None = None

        if self._quality not in _QUALITIES:
            raise AvatarEngineError(
                "HEYGEN_VIDEO_QUALITY invalido: "
                f"{self._quality!r}. Use um de: {', '.join(_QUALITIES)}."
            )

    async def start(self, session: Any, room: Any) -> None:
        if not self._api_key:
            raise AvatarEngineError("HEYGEN_API_KEY nao definido.")
        if not self._avatar_id:
            raise AvatarEngineError("HEYGEN_AVATAR_ID nao definido.")

        try:
            from livekit.plugins import liveavatar
        except ImportError as exc:  # pragma: no cover
            raise AvatarEngineError(
                "Plugin ausente. Instale: pip install livekit-plugins-liveavatar"
            ) from exc

        self._session = liveavatar.AvatarSession(
            avatar_id=self._avatar_id,
            video_quality=self._quality,
        )
        logger.info(
            "iniciando avatar heygen avatar_id=%s quality=%s",
            self._avatar_id,
            self._quality,
        )
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
        except Exception:  # pragma: no cover - encerrar nunca derruba a sessao
            logger.exception("falha ao encerrar avatar heygen")
        finally:
            self._session = None

    async def health(self, deep: bool = False) -> Health:
        if not self._api_key:
            return Health(False, self.name, "HEYGEN_API_KEY ausente")
        if not self._avatar_id:
            return Health(False, self.name, "HEYGEN_AVATAR_ID ausente")
        if deep:
            try:
                import livekit.plugins.liveavatar  # noqa: F401
            except ImportError:
                return Health(
                    False, self.name, "livekit-plugins-liveavatar nao instalado"
                )
        return Health(True, self.name, f"avatar_id={self._avatar_id}")
