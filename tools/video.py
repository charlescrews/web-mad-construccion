#!/usr/bin/env python3
"""Prepara un vídeo para servirlo desde la web (bloque :::video): MP4 H.264 que se reproduce en cualquier navegador, empieza a verse
antes de descargarse entero (faststart), sin metadatos (ubicación GPS, móvil, fecha) y con una imagen de portada.

    # necesita ffmpeg (apt install ffmpeg / brew install ffmpeg)
    python tools/video.py originales/horno.mov static/video/                 # → static/video/horno.mp4 + horno-poster.webp
    python tools/video.py originales/horno.mov static/video/ --alto 1080 --sin-audio --portada 3.5

Por defecto 720 px de alto, calidad CRF 26 y audio AAC a 128 kbps. Avisa a partir de 15 MB y falla por encima de 30 MB (lo mismo que
build.py): un vídeo más largo, mejor en YouTube con «youtube:». Los subtítulos (.vtt) no se generan aquí: transcripción revisada a mano
(skill fotografia-video-cliente). Al final imprime el bloque :::video para pegar en la página.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

AVISO_MB, MAX_MB = 15, 30


def slug(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "video"


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def convert(src: Path, out_dir: Path, alto: int = 720, crf: int = 26, sin_audio: bool = False, portada: float = 1.0) -> tuple[Path, Path]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("Falta ffmpeg (apt install ffmpeg / brew install ffmpeg)")
    out_dir.mkdir(parents=True, exist_ok=True)
    base = slug(src.stem)
    mp4, poster = out_dir / f"{base}.mp4", out_dir / f"{base}-poster.webp"
    audio = ["-an"] if sin_audio else ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-map", "0:v:0", *([] if sin_audio else ["-map", "0:a:0?"]),
                    # sin metadatos ni capítulos: fuera ubicación, modelo del móvil y fecha
                    "-map_metadata", "-1", "-map_chapters", "-1",
                    "-vf", f"scale=-2:'min({alto},ih)'", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
                    "-pix_fmt", "yuv420p", "-profile:v", "high", *audio, "-movflags", "+faststart", str(mp4)], check=True)
    dur = float(probe(mp4)["format"].get("duration", 0) or 0)
    at = min(max(portada, 0), max(dur - 0.1, 0))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(mp4), "-frames:v", "1", "-map_metadata", "-1",
                    "-c:v", "libwebp", "-quality", "80", str(poster)], check=True)
    return mp4, poster


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origen")
    ap.add_argument("destino")
    ap.add_argument("--alto", type=int, default=720)
    ap.add_argument("--crf", type=int, default=26)
    ap.add_argument("--sin-audio", action="store_true", help="quita el sonido (vídeos de ambiente: entonces «sin_voz: true»)")
    ap.add_argument("--portada", type=float, default=1.0, help="segundo del que se saca la imagen de portada")
    a = ap.parse_args()
    mp4, poster = convert(Path(a.origen), Path(a.destino), a.alto, a.crf, a.sin_audio, a.portada)
    mb = mp4.stat().st_size / 1e6
    print(f"{mp4} ({mb:.1f} MB) y {poster}")
    rel = lambda p: p.as_posix().split("static/", 1)[-1]  # noqa: E731
    print(f"\n:::video\ntitulo: [CONFIRMAR: qué se ve]\narchivo: {rel(mp4)}\nposter: {rel(poster)}\n"
          + ("sin_voz: true\n" if a.sin_audio else f"subtitulos: {rel(mp4.with_suffix('.es.vtt'))}\n") + ":::")
    if mb > MAX_MB:
        print(f"ERROR: más de {MAX_MB} MB: build.py no lo publicará. Baja --alto, sube --crf o publícalo en YouTube.")
        return 1
    if mb > AVISO_MB:
        print(f"AVISO: más de {AVISO_MB} MB: tarda en cargar con datos móviles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
