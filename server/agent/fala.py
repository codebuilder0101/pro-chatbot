"""Deixa texto de tela pronto para ser lido em voz alta.

O fluxo do n8n foi escrito para o WhatsApp: emoji em quase toda resposta,
separadores `---`, negrito com asteriscos, listas com marcador. Na tela isso
ajuda; no sintetizador de voz vira "traco traco traco" ou um emoji lido pelo
nome. Nenhum dos dois soa como uma pessoa falando.

Este modulo tira o que a voz nao consegue falar. Nao muda palavras, nao
resume, nao reescreve: o conteudo clinico e do cliente e continua identico.
"""

from __future__ import annotations

import re

# Emojis e simbolos pictograficos, incluindo variantes e o ZWJ que cola
# emojis compostos.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "⬀-⯿"
    "️‍]+"
)

# Separadores e titulos de markdown no inicio da linha: ---, ***, ___, ###
_MARKDOWN = re.compile(r"(^|\n)[ \t]*(?:-{3,}|\*{3,}|_{3,}|#{1,6}[ \t]*)")

# **negrito** e _italico_: fica so o miolo
_ENFASE = re.compile(r"\*{1,2}([^*\n]+)\*{1,2}|_{1,2}([^_\n]+)_{1,2}")

# Marcador de lista no inicio da linha
_MARCADOR = re.compile(r"(^|\n)[ \t]*[-*•][ \t]+")

_ESPACOS = re.compile(r"[ \t]{2,}")
_QUEBRAS = re.compile(r"\n{2,}")


def para_fala(texto: str) -> str:
    t = _EMOJI.sub("", texto)
    t = _MARKDOWN.sub(r"\1", t)
    t = _ENFASE.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _MARCADOR.sub(r"\1", t)
    t = _ESPACOS.sub(" ", t)
    t = _QUEBRAS.sub("\n", t)
    return t.strip()
