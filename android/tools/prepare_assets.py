"""Gera os recursos Android a partir dos originais em /assets.

Rodar da raiz do repositorio:
    server/.venv/Scripts/python.exe android/tools/prepare_assets.py

Existe para que ninguem precise abrir editor de imagem quando a marca mudar.
Trocou o PNG em /assets, roda de novo, recompila.

O que produz:
  drawable-nodpi/iara_logo.png      wordmark da home
  drawable-nodpi/iara_avatar.png    rosto da IARA, placeholder da chamada
  mipmap-*/ic_launcher_foreground   selo circular recortado da logo
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
RES = ROOT / "android" / "app" / "src" / "main" / "res"

LOGO_SRC = ASSETS / "LOGO OF TRANSP S GRAD.png"
AVATAR_SRC = ASSETS / "IMAGEM OF TRANSP.png"

# Um PNG unico em drawable-nodpi e' decodificado no tamanho cheio em qualquer
# aparelho, na thread principal, durante a composicao. Num telefone
# intermediario isso e' um engasgo visivel; no emulador com renderizacao por
# software chega a dar ANR. Por isso cada densidade recebe o seu tamanho.
#
# O circulo da chamada ocupa 82% da largura da tela, ou seja ~295 dp. Os
# numeros abaixo cobrem isso em cada densidade, com um teto em 1024 porque
# acima disso a diferenca nao aparece num rosto e o bitmap so' engorda.
AVATAR_BY_DENSITY = {
    "mdpi": 320,
    "hdpi": 480,
    "xhdpi": 640,
    "xxhdpi": 896,
    "xxxhdpi": 1024,
}
LOGO_BY_DENSITY = {
    "mdpi": 340,
    "hdpi": 500,
    "xhdpi": 680,
    "xxhdpi": 1000,
    "xxxhdpi": 1340,
}

# Densidades do icone adaptativo: 108 dp de lado.
LAUNCHER_DENSITIES = {
    "mdpi": 108,
    "hdpi": 162,
    "xhdpi": 216,
    "xxhdpi": 324,
    "xxxhdpi": 432,
}
# A mascara do Android come as bordas. O desenho fica nos 66% centrais para
# nao ser cortado em telefone que usa mascara circular.
LAUNCHER_SAFE_RATIO = 0.66


def require(path: Path) -> None:
    if not path.exists():
        sys.exit(f"arquivo nao encontrado: {path}")


def trim_transparent(img: Image.Image) -> Image.Image:
    """Corta a moldura transparente em volta do desenho."""
    box = img.getbbox()
    return img.crop(box) if box else img


def save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    kb = path.stat().st_size / 1024
    print(f"  {path.relative_to(ROOT)}  {img.width}x{img.height}  {kb:.0f} KB")


def build_avatar() -> None:
    print("avatar:")
    img = Image.open(AVATAR_SRC).convert("RGBA")
    img = trim_transparent(img)

    # A arte ja vem redonda. Deixamos quadrada para o recorte circular do
    # Compose cair exatamente sobre a borda, sem faixa transparente.
    side = max(img.width, img.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))

    for density, size in AVATAR_BY_DENSITY.items():
        save(
            canvas.resize((size, size), Image.LANCZOS),
            RES / f"drawable-{density}" / "iara_avatar.png",
        )


def build_logo() -> None:
    print("logo:")
    img = Image.open(LOGO_SRC).convert("RGBA")
    img = trim_transparent(img)
    for density, width in LOGO_BY_DENSITY.items():
        height = round(img.height * width / img.width)
        save(
            img.resize((width, height), Image.LANCZOS),
            RES / f"drawable-{density}" / "iara_logo.png",
        )


def build_launcher() -> None:
    """Recorta o selo circular da esquerda da logo e vira icone do app."""
    print("icone do app:")
    img = Image.open(LOGO_SRC).convert("RGBA")
    img = trim_transparent(img)

    # O selo encosta na letra "I" do wordmark, entao procurar uma coluna
    # transparente entre os dois nao funciona - nao existe. Usamos a geometria:
    # o selo e' circular, logo a altura da tinta numa faixa bem a esquerda
    # (onde so' existe o selo) da o diametro, e o recorte sai quadrado.
    # Duas armadilhas neste arquivo:
    #  - ha um halo suave (alpha 1..8) espalhado bem alem do desenho, e
    #    getbbox() conta isso como tinta;
    #  - o selo e' seguido pelo wordmark, que nao pode entrar no recorte.
    # Entao trabalhamos so' com tinta solida e pegamos a primeira faixa
    # continua de colunas: e' o selo.
    solid = img.getchannel("A").point(lambda v: 255 if v > 32 else 0)

    inked = [x for x in range(solid.width) if solid.crop((x, 0, x + 1, solid.height)).getbbox()]
    if not inked:
        sys.exit("logo sem tinta solida; confira o arquivo em /assets")

    left = inked[0]
    right = left
    for x in inked[1:]:
        if x - right > 1:
            break
        right = x

    band = solid.crop((left, 0, right + 1, solid.height)).getbbox()
    top, bottom = band[1], band[3]
    square = img.crop((left, top, right + 1, bottom))
    print(f"  selo: x {left}..{right}, y {top}..{bottom} -> {square.width}x{square.height}")

    # quadra o recorte para a mascara circular do Android nao deformar
    side = max(square.width, square.height)
    padded = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    padded.paste(square, ((side - square.width) // 2, (side - square.height) // 2))
    square = padded

    for density, full in LAUNCHER_DENSITIES.items():
        inner = round(full * LAUNCHER_SAFE_RATIO)
        art = square.resize((inner, inner), Image.LANCZOS)
        canvas = Image.new("RGBA", (full, full), (0, 0, 0, 0))
        canvas.paste(art, ((full - inner) // 2, (full - inner) // 2), art)
        save(canvas, RES / f"mipmap-{density}" / "ic_launcher_foreground.png")


if __name__ == "__main__":
    require(LOGO_SRC)
    require(AVATAR_SRC)
    build_avatar()
    build_logo()
    build_launcher()
    print("\npronto. recompile o app para ver.")
