#!/usr/bin/env python3
"""Prepara fotos para la web: redimensiona, convierte a WebP, quita metadatos (GPS, cámara, autor) y avisa del peso.

    pip install Pillow
    python tools/images.py fotos-del-cliente/ static/img/          # procesa una carpeta
    python tools/images.py foto.jpg static/img/ --width 1200        # una imagen, ancho máximo distinto
    python tools/images.py fotos/ static/img/ --variantes 480,960   # además foto-480.webp y foto-960.webp (srcset en build.py)
    python tools/images.py portada.jpg static/ --recorte 1200x630 --nombre og --png   # imagen para compartir (static/og.png)

Por defecto: ancho máximo 1600 px (fotos de portada) y calidad 80. Nombres en minúsculas y con guiones.
--recorte AxB recorta al centro con esa proporción y la deja a ese tamaño (og.png 1200x630; redes 1080x1350). Skill fotografia-video-cliente.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Falta Pillow: pip install Pillow")

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def slug(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "imagen"


def process(src: Path, out_dir: Path, width: int, quality: int, variantes: list[int] | None = None,
            recorte: tuple[int, int] | None = None, nombre: str | None = None, png: bool = False) -> list[Path]:
    out = []
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # respeta la orientación de las fotos del móvil
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        if recorte:
            im = ImageOps.fit(im, recorte, Image.LANCZOS, centering=(0.5, 0.5))
        elif im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        base = slug(nombre or src.stem)
        # Se guarda una imagen nueva, sin info EXIF/XMP/ICC de la original: fuera GPS, cámara, autor y fecha.
        clean = Image.new(im.mode, im.size)
        clean.paste(im)
        if png:
            dest = out_dir / f"{base}.png"
            clean.save(dest, "PNG", optimize=True)
        else:
            dest = out_dir / f"{base}.webp"
            clean.save(dest, "WEBP", quality=quality, method=6)
        out.append(dest)
        for w in sorted(set(variantes or [])):
            if recorte or png or w >= clean.width:
                continue
            v = clean.resize((w, round(clean.height * w / clean.width)), Image.LANCZOS)
            vd = out_dir / f"{base}-{w}.webp"
            v.save(vd, "WEBP", quality=quality, method=6)
            out.append(vd)
    for d in out:
        kb = d.stat().st_size // 1024
        warn = "  << pesa mucho: baja --width o --quality" if kb > 300 else ""
        print(f"{src.name} -> {d.name} ({kb} KB){warn}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origen")
    ap.add_argument("destino")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--variantes", default="", help="anchos menores separados por comas (480,960): foto-480.webp…")
    ap.add_argument("--recorte", default="", help="AxB: recorte al centro a ese tamaño (1200x630)")
    ap.add_argument("--nombre", default="", help="nombre del archivo de salida (solo con una imagen)")
    ap.add_argument("--png", action="store_true", help="PNG en vez de WebP (og.png)")
    a = ap.parse_args()
    try:
        variantes = [int(x) for x in a.variantes.split(",") if x.strip()]
        recorte = tuple(int(x) for x in a.recorte.lower().split("x")) if a.recorte else None
    except ValueError:
        sys.exit("--variantes: números separados por comas; --recorte: ANCHOxALTO")
    if recorte and (len(recorte) != 2 or min(recorte) < 16):
        sys.exit("--recorte: ANCHOxALTO, p. ej. 1200x630")
    src, out = Path(a.origen), Path(a.destino)
    out.mkdir(parents=True, exist_ok=True)
    files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.suffix.lower() in EXTS)
    if not files:
        sys.exit("No hay imágenes en el origen")
    if a.nombre and len(files) > 1:
        sys.exit("--nombre solo con una imagen")
    for f in files:
        try:
            process(f, out, a.width, a.quality, variantes, recorte, a.nombre or None, a.png)
        except Exception as e:  # una foto rota no detiene el resto
            print(f"ERROR {f.name}: {e}")


if __name__ == "__main__":
    main()
