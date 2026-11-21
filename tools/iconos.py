#!/usr/bin/env python3
"""Iconos de la web instalable (site.json > app.pwa) a partir de un PNG cuadrado del logo o del símbolo de la marca.

    python tools/iconos.py simbolo.png                 # fondo: site.json > app.color_fondo (o brand.paper)
    python tools/iconos.py simbolo.png --fondo "#9A4B1C"

Genera en static/app/:
- icono-192.png e icono-512.png: el símbolo con un pequeño margen (Android, escritorio).
- icono-maskable-512.png: el símbolo dentro de la «zona segura» (círculo del 80 %), sobre fondo de color: Android lo recorta en
  círculo, gota o cuadrado según el móvil y no se puede comer el logo.
- apple-touch-icon.png (180 px): sin transparencias (iOS las pinta de negro).

El original debe medir 512 px o más por lado. Un logotipo con letras pequeñas no se lee a 48 px: mejor el símbolo o la inicial.
Necesita Pillow (pip install pillow).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "app"
# Zona segura de los iconos «maskable»: un círculo de diámetro 80 % del icono. Un cuadrado inscrito mide 0,8/√2 ≈ 0,566.
SAFE = 0.56


def hex_rgb(h: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", h or ""):
        sys.exit(f"ERROR: color no válido: {h} (#RRGGBB)")
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def make(src: Path, fondo: str, out: Path = OUT) -> list[Path]:
    from PIL import Image

    img = Image.open(src).convert("RGBA")
    w, h = img.size
    if min(w, h) < 512:
        sys.exit(f"ERROR: {src} mide {w}×{h}; hace falta un original de 512 px o más por lado")
    if abs(w - h) > max(w, h) * 0.02:
        print(f"AVISO: {src} no es cuadrado ({w}×{h}); se centra sin deformarlo")
    bbox = img.getbbox() or (0, 0, w, h)
    img = img.crop(bbox)
    bg = hex_rgb(fondo) + (255,)
    out.mkdir(parents=True, exist_ok=True)

    def place(size: int, frac: float, opaque: bool) -> "Image.Image":
        canvas = Image.new("RGBA", (size, size), bg if opaque else (0, 0, 0, 0))
        side = int(size * frac)
        logo = img.copy()
        logo.thumbnail((side, side), Image.LANCZOS)
        canvas.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
        return canvas.convert("RGB") if opaque else canvas

    files = {
        "icono-192.png": place(192, 0.84, opaque=True),
        "icono-512.png": place(512, 0.84, opaque=True),
        "icono-maskable-512.png": place(512, SAFE, opaque=True),
        "apple-touch-icon.png": place(180, 0.78, opaque=True),
    }
    written = []
    for name, im in files.items():
        p = out / name
        im.save(p, "PNG", optimize=True)
        written.append(p)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origen", type=Path)
    ap.add_argument("--fondo", help="color de fondo #RRGGBB (por defecto app.color_fondo o brand.paper)")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    fondo = a.fondo or (cfg.get("app") or {}).get("color_fondo") or cfg["brand"]["paper"]
    for p in make(a.origen, fondo):
        print(f"OK: {p.relative_to(ROOT)}")
    print("Revisa el icono «maskable» en un Android (círculo, gota, cuadrado) antes de publicar.")


if __name__ == "__main__":
    main()
