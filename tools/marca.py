#!/usr/bin/env python3
"""Identidad de marca del cliente en la web y su entrega (skill identidad-marca-cliente).

    python tools/marca.py revisar     # logo, favicon, fuentes (archivo, licencia y caracteres) y og.png; lo mismo hace check.py
    python tools/marca.py fuente fraunces [--version 5.3.0] [--estatica --pesos 400,700] [--italica] [--subconjunto latin]
    python tools/marca.py logotipo "La Espiga" --fuente static/fonts/fraunces-latin-wght-normal.woff2 --peso 650 \\
        [--eje opsz=72] [--simbolo marca/simbolo.svg] [--color "#2A211B"] [--espaciado 0] [--salida static/img/logo.svg]
    python tools/marca.py og [--foto static/img/portada.webp] [--texto "Pan de masa madre en Benalmádena"]
    python tools/marca.py kit         # marca/entrega/ y su zip: logos (SVG, PDF y PNG), avatar, favicon, og, fuentes y manual

Qué protege:
- Logo y favicon en SVG de verdad: sin scripts, eventos ni nada que se cargue de fuera; sin imágenes PNG/JPG metidas dentro (eso no es
  un vectorial); el logo sin texto vivo (se vería con otra tipografía en cada equipo: hay que pasarlo a trazos, `logotipo` lo hace);
  con viewBox; el favicon cuadrado; sin rutas del equipo de quien lo diseñó.
- Fuentes autoalojadas: woff2 que existe, con su licencia publicada al lado (la OFL exige distribuirla con la fuente), licencia
  reconocida (OFL, Apache, UFL o MIT; otra, revisada a mano con fecha); la primera familia de cada pila, autoalojada o del sistema
  (si no, en la mayoría de móviles se ve otra); y, con fontTools, que la fuente tenga todos los caracteres de la web (una «ñ» o una
  «ő» que falta sale con otra fuente).
- og.png de 1200×630 (lo que se ve al compartir en WhatsApp y redes).

`fuente` descarga del registro de npm (Fontsource) solo los woff2 pedidos y la licencia; nada se carga de Google. `logotipo`, `og`,
`kit` y la comprobación de caracteres necesitan fontTools y brotli (pip install fonttools==4.66.1 brotli==1.2.0); `og` y `kit`,
Playwright con Chromium. El kit no se genera si algo de la marca falla.
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Familias que no hace falta autoalojar: genéricas, la del sistema y las «seguras» que traen casi todos los equipos (en Android,
# Georgia o Arial no existen, pero la pila termina en serif/sans-serif y el cambio es el esperado).
GENERICAS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif", "ui-monospace",
             "ui-rounded", "math", "emoji", "fangsong"}
SISTEMA = {"-apple-system", "blinkmacsystemfont", "segoe ui", "roboto", "helvetica neue", "helvetica", "arial", "noto sans",
           "liberation sans", "ubuntu", "cantarell", "georgia", "times new roman", "times", "verdana", "tahoma", "trebuchet ms",
           "courier new", "menlo", "consolas", "apple color emoji", "segoe ui emoji", "noto color emoji", "segoe ui symbol"}
# Licencias que permiten publicar la fuente en la web (texto que las identifica, nombre corto).
LICENCIAS = [("SIL Open Font License", "OFL-1.1"), ("Apache License", "Apache-2.0"), ("Ubuntu Font Licence", "UFL-1.0"),
             ("Permission is hereby granted, free of charge", "MIT")]
LICENCIAS_NPM = {"OFL-1.1", "Apache-2.0", "UFL-1.0", "MIT"}
OG = (1200, 630)


# ---------------------------------------------------------------------------------------------------------------- utilidades

def cargar_cfg(root: Path = ROOT) -> dict:
    return json.loads((root / "site.json").read_text(encoding="utf-8"))


def familias(pila: str) -> list[str]:
    return [p.strip().strip("'\"").strip() for p in (pila or "").split(",") if p.strip().strip("'\"").strip()]


def hex_norm(c: str) -> str:
    c = c.strip().upper()
    return "#" + "".join(ch * 2 for ch in c[1:]) if re.fullmatch(r"#[0-9A-F]{3}", c) else c


def paleta(brand: dict) -> set[str]:
    return {hex_norm(v) for v in brand.values() if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", v.strip())}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def viewbox(texto: str) -> tuple[float, float, float, float] | None:
    m = re.search(r"<svg\b[^>]*?\bviewBox\s*=\s*[\"']([^\"']+)[\"']", texto, re.S)
    if not m:
        return None
    try:
        nums = [float(x) for x in re.split(r"[\s,]+", m.group(1).strip())]
    except ValueError:
        return None
    return tuple(nums) if len(nums) == 4 and nums[2] > 0 and nums[3] > 0 else None  # type: ignore[return-value]


def png_size(path: Path) -> tuple[int, int] | None:
    d = path.read_bytes()[:32]
    if d[:8] == b"\x89PNG\r\n\x1a\n" and d[12:16] == b"IHDR":
        return int.from_bytes(d[16:20], "big"), int.from_bytes(d[20:24], "big")
    return None


# ---------------------------------------------------------------------------------------------------------------- SVG

_COLOR_ATTR = re.compile(r"(?:^|[;\s\"'{])(?:fill|stroke|stop-color|color|flood-color)\s*:\s*(#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?)\b")


def svg_problemas(texto: str, tipo: str = "logo", colores: set[str] | None = None) -> tuple[list[str], list[str]]:
    """(errores, avisos) de un SVG de marca. tipo: logo | favicon | simbolo."""
    errs: list[str] = []
    warns: list[str] = []
    if re.search(r"<!ENTITY", texto, re.I):
        return ["declara entidades XML (<!ENTITY>), típico de exportaciones antiguas de Illustrator: volver a exportar como SVG sin "
                "entidades o limpiarlo"], []
    try:
        root = ET.fromstring(texto)
    except ET.ParseError as e:
        return [f"SVG mal formado ({e})"], []
    if _local(root.tag) != "svg":
        return ["no es un SVG (la raíz no es <svg>)"], []
    if re.search(r"<!DOCTYPE", texto, re.I):
        warns.append("lleva <!DOCTYPE>: sobra en un SVG para la web")
    texto_vivo = False
    for el in root.iter():
        name = _local(el.tag)
        if name == "script":
            errs.append("contiene <script>: un logo no ejecuta código")
        elif name == "foreignObject":
            errs.append("contiene <foreignObject> (HTML dentro del SVG): no sirve para un logo")
        elif name == "image":
            errs.append("lleva una imagen incrustada (<image>, normalmente un PNG o JPG): no es vectorial y se pixela; pedir el original "
                        "vectorial a quien lo diseñó")
        elif name in ("text", "tspan", "textPath"):
            texto_vivo = True
        for k, v in el.attrib.items():
            kl = _local(k).lower()
            if kl.startswith("on"):
                errs.append(f"atributo de evento «{kl}»: un logo no ejecuta código")
            if kl == "href" and re.match(r"\s*(?:https?:|//|javascript:)", v, re.I):
                errs.append(f"enlaza o carga algo de fuera ({v[:60]}): todo tiene que estar dentro del SVG")
            if kl == "style" and re.search(r"url\(\s*['\"]?\s*(?:https?:|//)|@import", v, re.I):
                errs.append("estilo que carga algo de fuera (url() o @import)")
        if name == "style" and re.search(r"url\(\s*['\"]?\s*(?:https?:|//)|@import", el.text or "", re.I):
            errs.append("hoja de estilo que carga algo de fuera (url() o @import, p. ej. una fuente de Google)")
    if texto_vivo:
        msg = ("texto sin convertir a trazos (<text>): cada equipo lo pinta con la fuente que tenga y el logo cambia; pasarlo a trazos "
               "(python tools/marca.py logotipo, o «Objeto a trayecto» en Inkscape)")
        (warns if tipo == "favicon" else errs).append(msg)
    if re.search(r"(?:/home/|/Users/|[A-Za-z]:\\\\|[A-Za-z]:\\(?=[^\\]))", texto):
        errs.append("contiene una ruta del equipo de quien lo diseñó (p. ej. inkscape:export-filename): limpiar el SVG antes de publicarlo")
    if re.search(r"\b(?:sodipodi|inkscape):|<metadata\b|xmlns:(?:x|i|graph)=|Adobe Illustrator", texto):
        warns.append("restos del programa de diseño (Inkscape o Illustrator): exportar como «SVG optimizado» o limpiarlo (pesa más y "
                     "puede llevar datos internos)")
    vb = viewbox(texto)
    if not vb:
        errs.append("sin viewBox: no escala bien (exportar con viewBox)")
    else:
        w, h = vb[2], vb[3]
        if tipo == "favicon" and abs(w - h) > 0.01 * max(w, h):
            errs.append(f"favicon no cuadrado (viewBox {w:g}×{h:g}): en la pestaña se deforma o se recorta")
        if tipo == "logo" and w / h > 6:
            warns.append(f"logo muy alargado ({w / h:.1f}:1): a 40 px de alto apenas se lee en el móvil; usar una versión compacta o apilada")
    peso = len(texto.encode("utf-8"))
    if peso > 30_000:
        warns.append(f"pesa {peso // 1024} KB: un logo limpio pesa unos pocos KB (SVG optimizado)")
    if colores:
        usados = {hex_norm(m) for m in _COLOR_ATTR.findall(texto)}
        for el in root.iter():
            for k in ("fill", "stroke", "stop-color", "color", "flood-color"):
                v = el.get(k, "")
                if re.fullmatch(r"\s*#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\s*", v):
                    usados.add(hex_norm(v))
        fuera = sorted(usados - colores - {"#FFFFFF", "#000000"})
        if fuera:
            warns.append(f"usa colores que no están en site.json > brand ({', '.join(fuera)}): ¿es el mismo color corporativo?")
    return errs, warns


# ---------------------------------------------------------------------------------------------------------------- fuentes

def fuentes_problemas(brand: dict, static: Path) -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warns: list[str] = []
    propias: dict[str, str] = {}
    for f in brand.get("font_files") or []:
        fam, fil = (f.get("family") or "").strip(), (f.get("file") or "").strip()
        if not fam or not fil:
            errs.append(f"brand.font_files: cada fuente lleva «family» y «file» ({f})")
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,60}", fam) or not re.fullmatch(r"[A-Za-z0-9._-]+\.woff2", fil):
            errs.append(f"brand.font_files: nombre de familia o de archivo con caracteres raros («{fam}», «{fil}»)")
            continue
        p = static / "fonts" / fil
        if not p.is_file():
            errs.append(f"brand.font_files: no existe static/fonts/{fil}")
            continue
        if p.read_bytes()[:4] != b"wOF2":
            errs.append(f"static/fonts/{fil}: no es un woff2 (python tools/marca.py fuente …)")
        if p.stat().st_size > 150_000:
            warns.append(f"static/fonts/{fil} pesa {p.stat().st_size // 1024} KB: usar el subconjunto latin o la variable de un solo eje")
        lic = (f.get("licencia") or "").strip()
        if not lic:
            errs.append(f"static/fonts/{fil}: falta «licencia» en font_files (el archivo de la licencia, en static/fonts/: se publica con "
                        "la fuente, como exige la OFL)")
        elif not re.fullmatch(r"[A-Za-z0-9._-]+", lic) or not (static / "fonts" / lic).is_file():
            errs.append(f"static/fonts/{fil}: no existe la licencia static/fonts/{lic}")
        else:
            t = (static / "fonts" / lic).read_text(encoding="utf-8", errors="replace")
            if not any(s in t for s, _ in LICENCIAS) and not f.get("licencia_revisada"):
                errs.append(f"static/fonts/{lic}: licencia que no es OFL, Apache, UFL ni MIT: comprobar que permite publicarla en la web (y "
                            "cuántas visitas cubre) y anotar «licencia_revisada» con la fecha")
            if re.search(r"with Reserved Font Name", t, re.I):
                warns.append(f"{fam}: su licencia reserva el nombre: si se recorta o modifica la fuente hay que cambiarle el nombre "
                             "(FAQ de la OFL, 2.6); los archivos de Fontsource ya vienen así de su autor")
        propias.setdefault(fam.lower(), fam)
    usadas: set[str] = set()
    for key in ("font_heading", "font_body"):
        pila = familias(brand.get(key, ""))
        if not pila:
            continue
        usadas.update(p.lower() for p in pila)
        primera = pila[0].lower()
        if primera not in propias and primera not in GENERICAS | SISTEMA:
            errs.append(f"brand.{key}: «{pila[0]}» no está en font_files ni es del sistema: quien no la tenga instalada (casi todos los "
                        "móviles) verá otra. Autoalojarla: python tools/marca.py fuente …")
        if pila[-1].lower() not in GENERICAS:
            warns.append(f"brand.{key}: la pila termina sin familia genérica (serif, sans-serif o system-ui)")
    for k, fam in propias.items():
        if k not in usadas:
            warns.append(f"brand.font_files: «{fam}» está declarada pero no se usa en font_heading ni font_body")
    if len(propias) > 2:
        warns.append(f"{len(propias)} familias propias: con dos basta (más peso y menos coherencia)")
    return errs, warns


class _Texto(HTMLParser):
    """Texto visible de una página y, aparte, el de los títulos (h1-h3 y el nombre de la cabecera usan font_heading)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.todo: list[str] = []
        self.titulos: list[str] = []
        self._skip = 0
        self._tit = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template"):
            self._skip += 1
        if tag in ("h1", "h2", "h3") or (tag == "a" and "brand" in (dict(attrs).get("class") or "").split()):
            self._tit += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template") and self._skip:
            self._skip -= 1
        if (tag in ("h1", "h2", "h3") or tag == "a") and self._tit:
            self._tit -= 1

    def handle_data(self, data):
        if self._skip:
            return
        self.todo.append(data)
        if self._tit:
            self.titulos.append(data)


def _cuenta(c: str) -> bool:
    """Caracteres que una fuente de texto debe tener: letras, números, puntuación y monedas (los símbolos y emojis caen a otra)."""
    cat = unicodedata.category(c)
    return cat[0] in "LNP" or cat == "Sc"


def hay_fonttools() -> bool:
    try:
        import brotli  # noqa: F401
        import fontTools.ttLib  # noqa: F401
    except ImportError:
        return False
    return True


def glifos_faltan(public: Path, brand: dict, static: Path) -> list[str] | None:
    """Caracteres de la web que no tiene la fuente propia que los pinta. None si no hay fontTools y brotli."""
    if not hay_fonttools():
        return None
    from fontTools.ttLib import TTFont

    cmaps: dict[str, set[int]] = {}
    for f in brand.get("font_files") or []:
        p = static / "fonts" / str(f.get("file", ""))
        if p.is_file() and p.read_bytes()[:4] == b"wOF2":
            cmaps.setdefault(str(f.get("family", "")).lower(), set()).update(TTFont(p).getBestCmap().keys())
    if not cmaps:
        return []
    body = (familias(brand.get("font_body", "")) or [""])[0].lower()
    head = (familias(brand.get("font_heading", "")) or [""])[0].lower()
    donde: dict[tuple[str, str], str] = {}
    for page in sorted(public.rglob("*.html")):
        p = _Texto()
        p.feed(page.read_text(encoding="utf-8", errors="replace"))
        rel = str(page.relative_to(public))
        for fam, trozos in ((body, p.todo), (head, p.titulos)):
            if fam not in cmaps:
                continue
            for c in set("".join(trozos)):
                if _cuenta(c) and ord(c) not in cmaps[fam]:
                    donde.setdefault((fam, c), rel)
    nombres = {str(f.get("family", "")).lower(): f.get("family") for f in brand.get("font_files") or []}
    return [f"la fuente «{nombres[fam]}» no tiene «{c}» (U+{ord(c):04X}), que sale en {rel}: se verá con otra fuente; usar un subconjunto "
            "que lo incluya (python tools/marca.py fuente … --subconjunto latin-ext)" for (fam, c), rel in sorted(donde.items())]


# ---------------------------------------------------------------------------------------------------------------- og.png

def og_problemas(path: Path) -> list[str]:
    size = png_size(path)
    if size is None:
        return ["static/og.png no es un PNG"]
    if size != OG:
        return [f"static/og.png mide {size[0]}×{size[1]}: tiene que medir 1200×630 (si no, WhatsApp y las redes la recortan o no la "
                "enseñan); python tools/marca.py og"]
    return []


def revisar(root: Path = ROOT, public: Path | None = None) -> tuple[list[str], list[str]]:
    """Todo lo de la marca (lo llama tools/check.py sobre public/ y `marca.py revisar` sobre static/)."""
    cfg = cargar_cfg(root)
    brand = cfg["brand"]
    static = root / "static"
    base = public or static
    colores = paleta(brand)
    errs: list[str] = []
    warns: list[str] = []
    logo = brand.get("logo")
    if logo:
        p = base / logo
        if not p.is_file():
            errs.append(f"brand.logo: no existe static/{logo}")
        elif p.suffix.lower() == ".svg":
            e, w = svg_problemas(p.read_text(encoding="utf-8", errors="replace"), "logo", colores)
            errs += [f"logo (static/{logo}): {x}" for x in e]
            warns += [f"logo (static/{logo}): {x}" for x in w]
        else:
            warns.append(f"brand.logo es {p.suffix}: mejor el SVG (se ve nítido en cualquier pantalla y pesa menos)")
    fav = base / "favicon.svg"
    if fav.is_file():
        e, w = svg_problemas(fav.read_text(encoding="utf-8", errors="replace"), "favicon", colores)
        errs += [f"favicon (static/favicon.svg): {x}" for x in e]
        warns += [f"favicon (static/favicon.svg): {x}" for x in w]
    e, w = fuentes_problemas(brand, static)
    errs += e
    warns += w
    og = base / "og.png"
    if og.is_file():
        errs += og_problemas(og)
    if public is not None:
        faltan = glifos_faltan(public, brand, static)
        if faltan is None:
            if brand.get("font_files"):
                warns.append("sin fontTools y brotli no se comprueba que las fuentes tengan todos los caracteres de la web "
                             "(pip install fonttools==4.66.1 brotli==1.2.0; GitHub Actions lo hace)")
        else:
            errs += faltan
    return errs, warns


# ---------------------------------------------------------------------------------------------------------------- fuente (npm)

def fuente(paquete: str, *, version: str = "", estatica: bool = False, pesos: list[int] | None = None, italica: bool = False,
           subconjunto: str = "latin", destino: Path | None = None, tgz: Path | None = None) -> list[dict]:
    """Copia de un paquete de Fontsource solo los woff2 pedidos y la licencia. Devuelve las entradas de brand.font_files."""
    destino = destino or ROOT / "static" / "fonts"
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", paquete):
        raise SystemExit(f"ERROR: «{paquete}» no es un id de Fontsource (minúsculas y guiones, como en fontsource.org/fonts/<id>)")
    if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", subconjunto):
        raise SystemExit(f"ERROR: subconjunto no válido: {subconjunto}")
    npm = f"@fontsource{'' if estatica else '-variable'}/{paquete}"
    tmp = Path(tempfile.mkdtemp(prefix="fuente-"))
    try:
        if tgz is None:
            if not version:
                r = subprocess.run(["npm", "view", npm, "version"], capture_output=True, text=True)
                if r.returncode:
                    raise SystemExit(f"ERROR: npm no encuentra {npm}: {r.stderr.strip()[:200]}")
                version = r.stdout.strip()
            if not re.fullmatch(r"\d+\.\d+\.\d+", version):
                raise SystemExit(f"ERROR: versión no válida: {version}")
            r = subprocess.run(["npm", "pack", f"{npm}@{version}", "--pack-destination", str(tmp), "--silent"], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"ERROR: npm pack {npm}@{version}: {r.stderr.strip()[:200]}")
            tgz = next(tmp.glob("*.tgz"))
        with tarfile.open(tgz) as t:
            def leer(name: str) -> bytes | None:
                try:
                    m = t.getmember(f"package/{name}")
                except KeyError:
                    return None
                fh = t.extractfile(m) if m.isfile() else None
                return fh.read() if fh else None

            pkg = json.loads(leer("package.json") or b"{}")
            meta = json.loads(leer("metadata.json") or b"{}")
            lic = pkg.get("license") or (meta.get("license") or {}).get("type")
            if lic not in LICENCIAS_NPM:
                raise SystemExit(f"ERROR: {npm}: licencia «{lic}»: solo OFL-1.1, Apache-2.0, UFL-1.0 o MIT sin revisarla a mano")
            version = version or pkg.get("version", "")
            fam = meta.get("family") or paquete.replace("-", " ").title()
            if subconjunto not in (meta.get("subsets") or [subconjunto]):
                raise SystemExit(f"ERROR: {fam} no tiene el subconjunto {subconjunto} (tiene: {', '.join(meta.get('subsets') or [])})")
            estilos = ["normal"] + (["italic"] if italica else [])
            if estatica:
                pesos = pesos or [400, 700]
                quiero = [(f"{paquete}-{subconjunto}-{w}-{e}.woff2", str(w), e) for w in pesos for e in estilos]
            else:
                ejes = (meta.get("variable") or {})
                if "wght" not in ejes:
                    raise SystemExit(f"ERROR: {fam} no es variable en peso (wght): usar --estatica --pesos 400,700")
                rango = f"{int(float(ejes['wght'].get('min', 100)))} {int(float(ejes['wght'].get('max', 900)))}"
                quiero = [(f"{paquete}-{subconjunto}-wght-{e}.woff2", rango, e) for e in estilos]
            licencia = leer("LICENSE")
            if not licencia:
                raise SystemExit(f"ERROR: {npm} no trae LICENSE: no se puede publicar la fuente sin su licencia")
            destino.mkdir(parents=True, exist_ok=True)
            out = []
            for name, peso, estilo in quiero:
                data = leer(f"files/{name}")
                if not data or data[:4] != b"wOF2":
                    raise SystemExit(f"ERROR: {npm}@{version} no trae files/{name}")
                (destino / name).write_bytes(data)
                out.append({"family": fam, "file": name, "weight": peso, "style": estilo, "licencia": f"{paquete}-LICENSE.txt",
                            "origen": f"{npm}@{version}"})
            (destino / f"{paquete}-LICENSE.txt").write_bytes(licencia)
            return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------- logotipo

def _abrir_fuente(path: Path, peso: float | None, ejes: dict[str, float]):
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    if "fvar" in font:
        from fontTools.varLib import instancer

        limites: dict[str, float | None] = {a.axisTag: None for a in font["fvar"].axes}  # None: cada eje en su valor por defecto
        if peso is not None:
            if "wght" not in limites:
                raise SystemExit("ERROR: la fuente no tiene eje de peso (wght)")
            limites["wght"] = peso
        for k, v in ejes.items():
            if k not in limites:
                raise SystemExit(f"ERROR: la fuente no tiene el eje {k} (tiene: {', '.join(limites)})")
            limites[k] = v
        font = instancer.instantiateVariableFont(font, limites)
    elif peso is not None or ejes:
        raise SystemExit("ERROR: --peso y --eje solo valen con fuentes variables; con una estática, elige el archivo del peso")
    return font


def _kerning(font, glifos: list[str]) -> list[float]:
    """Ajuste entre cada par de letras según la tabla de kerning (GPOS «kern», formatos 1 y 2). Sin él, el logotipo queda «flojo»."""
    adj = [0.0] * max(0, len(glifos) - 1)
    if "GPOS" not in font:
        return adj
    gpos = font["GPOS"].table
    idx = sorted({i for fr in gpos.FeatureList.FeatureRecord if fr.FeatureTag == "kern" for i in fr.Feature.LookupListIndex})
    for n in range(len(adj)):
        a, b = glifos[n], glifos[n + 1]
        for li in idx:
            lk = gpos.LookupList.Lookup[li]
            for st in lk.SubTable:
                if lk.LookupType == 9:
                    st = st.ExtSubTable
                if type(st).__name__ != "PairPos" or a not in st.Coverage.glyphs:
                    continue
                if st.Format == 1:
                    rec = next((r for r in st.PairSet[st.Coverage.glyphs.index(a)].PairValueRecord if r.SecondGlyph == b), None)
                    if rec is None:
                        continue
                    adj[n] += getattr(rec.Value1, "XAdvance", 0) or 0
                elif st.Format == 2:
                    c1 = st.ClassDef1.classDefs.get(a, 0)
                    c2 = st.ClassDef2.classDefs.get(b, 0)
                    adj[n] += getattr(st.Class1Record[c1].Class2Record[c2].Value1, "XAdvance", 0) or 0
                break
    return adj


def _num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def logotipo(texto: str, fuente_path: Path, *, peso: float | None = None, ejes: dict[str, float] | None = None, color: str = "#000000",
             simbolo: Path | None = None, espaciado: float = 0.0, altura_simbolo: float = 1.6) -> str:
    """SVG del nombre en trazos (sin texto vivo), con kerning y, si se da, el símbolo a la izquierda."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen

    if not texto.strip():
        raise SystemExit("ERROR: el logotipo necesita texto")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise SystemExit(f"ERROR: color no válido: {color} (#RRGGBB)")
    font = _abrir_fuente(fuente_path, peso, ejes or {})
    cmap = font.getBestCmap()
    faltan = sorted({c for c in texto if ord(c) not in cmap})
    if faltan:
        raise SystemExit(f"ERROR: la fuente no tiene {', '.join(faltan)}: elegir otra o un subconjunto que los incluya")
    gs = font.getGlyphSet()
    upm = font["head"].unitsPerEm
    nombres = [cmap[ord(c)] for c in texto]
    kern = _kerning(font, nombres)
    track = espaciado * upm
    xs, x = [], 0.0
    for i, g in enumerate(nombres):
        xs.append(x)
        x += gs[g].width + track + (kern[i] if i < len(kern) else 0)
    # Escala: 100 unidades por em; y hacia abajo (SVG). Primero los límites de la tinta, luego el trazado.
    k = 100 / upm
    bp = BoundsPen(gs)
    for g, gx in zip(nombres, xs):
        gs[g].draw(TransformPen(bp, (k, 0, 0, -k, gx * k, 0)))
    if not bp.bounds:
        raise SystemExit("ERROR: el texto no tiene trazos")
    x0, y0, x1, y1 = bp.bounds
    tw, th = x1 - x0, y1 - y0
    pad = 1.0
    if simbolo:
        st = simbolo.read_text(encoding="utf-8")
        e, _ = svg_problemas(st, "simbolo")
        if e:
            raise SystemExit("ERROR: símbolo: " + "; ".join(e))
        svb = viewbox(st)
        sh = th * altura_simbolo
        ss = sh / svb[3]
        sw = svb[2] * ss
        gap = sh * 0.35
        alto = sh + 2 * pad
        tx = pad + sw + gap - x0
        ty = pad + (sh - th) / 2 - y0
        ancho = pad + sw + gap + tw + pad
    else:
        alto = th + 2 * pad
        tx, ty = pad - x0, pad - y0
        ancho = tw + 2 * pad
    sp = SVGPathPen(gs, ntos=_num)
    for g, gx in zip(nombres, xs):
        gs[g].draw(TransformPen(sp, (k, 0, 0, -k, gx * k + tx, ty)))
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    root = ET.Element(f"{{{SVG_NS}}}svg", {"viewBox": f"0 0 {_num(ancho)} {_num(alto)}", "role": "img", "aria-label": texto})
    ET.SubElement(root, f"{{{SVG_NS}}}title").text = texto
    if simbolo:
        sroot = ET.fromstring(st)
        g = ET.SubElement(root, f"{{{SVG_NS}}}g", {"transform": f"translate({_num(pad - svb[0] * ss)} {_num(pad - svb[1] * ss)}) scale({ss:.5g})"})
        for ch in list(sroot):
            if _local(ch.tag) not in ("title", "desc", "metadata"):
                g.append(ch)
    ET.SubElement(root, f"{{{SVG_NS}}}path", {"fill": color.upper(), "d": sp.getCommands()})
    return ET.tostring(root, encoding="unicode") + "\n"


# ---------------------------------------------------------------------------------------------------------------- navegador

def _data_url(path: Path) -> str:
    mime = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".woff2": "font/woff2"}.get(path.suffix.lower())
    if not mime:
        raise SystemExit(f"ERROR: formato no admitido: {path.name}")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


class Navegador:
    """Chromium sin red: todo va en data: (nada sale a Internet; lo comprueban los tests con `peticiones`)."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch()
        self.peticiones: list[str] = []
        self.consola: list[str] = []
        return self

    def pagina(self, w: int, h: int, scale: float = 1):
        ctx = self.browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale)
        ctx.route("**/*", lambda r: (self.peticiones.append(r.request.url), r.abort()) if not r.request.url.startswith(("data:", "about:")) else r.continue_())
        page = ctx.new_page()
        page.on("console", lambda m: self.consola.append(m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self.consola.append(str(e)))
        return page

    def __exit__(self, *exc):
        self.browser.close()
        self._pw.stop()


def _font_faces(brand: dict, static: Path) -> str:
    return "".join(f"@font-face{{font-family:'{f['family']}';src:url({_data_url(static / 'fonts' / f['file'])}) format('woff2');"
                   f"font-weight:{f.get('weight', '100 900')};font-style:{f.get('style', 'normal')}}}"
                   for f in brand.get("font_files") or [] if (static / "fonts" / str(f.get("file", ""))).is_file())


def og(root: Path = ROOT, foto: Path | None = None, texto: str = "", nav: "Navegador | None" = None) -> Path:
    """static/og.png 1200×630: la foto (si hay) y el logo en un recuadro claro; sin foto, el logo sobre el fondo de la marca."""
    cfg = cargar_cfg(root)
    b = cfg["brand"]
    static = root / "static"
    logo = static / b["logo"] if b.get("logo") else None
    if not logo or not logo.is_file():
        raise SystemExit("ERROR: og.png necesita brand.logo")
    if foto and not foto.is_file():
        raise SystemExit(f"ERROR: no existe {foto}")
    txt = f'<p>{html.escape(texto)}</p>' if texto else ""
    if foto:
        cuerpo = (f'<div class="foto" style="background-image:url({_data_url(foto)})"></div>'
                  f'<div class="panel"><img src="{_data_url(logo)}" alt="">{txt}</div>')
    else:
        cuerpo = f'<div class="centro"><img src="{_data_url(logo)}" alt="">{txt}</div><div class="banda"></div>'
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>og</title><style>{_font_faces(b, static)}
html,body{{margin:0;width:1200px;height:630px;overflow:hidden;background:{b['paper']};font-family:{b['font_heading']}}}
.foto{{position:absolute;inset:0;background-size:cover;background-position:center}}
.panel{{position:absolute;left:56px;bottom:56px;max-width:760px;background:{b['paper']};border-radius:{b.get('radius', '8px')};padding:28px 36px}}
.panel img{{height:96px;max-width:680px;object-fit:contain;display:block}}
.centro{{position:absolute;inset:0 0 28px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px}}
.centro img{{max-width:880px;max-height:240px;object-fit:contain}}
p{{margin:16px 0 0;color:{b['ink']};font-size:36px;line-height:1.2;max-width:880px;text-align:center}}
.panel p{{text-align:left;font-size:30px}}
.banda{{position:absolute;left:0;right:0;bottom:0;height:28px;background:{b['primary']}}}</style></head><body>{cuerpo}</body></html>"""
    out = static / "og.png"
    propio = nav is None
    nav = nav or Navegador().__enter__()
    try:
        page = nav.pagina(*OG)
        page.set_content(doc, wait_until="load")
        page.evaluate("document.fonts.ready.then(() => true)")
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": OG[0], "height": OG[1]})
        page.context.close()
    finally:
        if propio:
            nav.__exit__(None, None, None)
    return out


# ---------------------------------------------------------------------------------------------------------------- manual y kit

USOS_INCORRECTOS = ["Deformarlo (estirarlo o aplastarlo): se escala siempre con las proporciones bloqueadas.",
                    "Cambiarle los colores, añadirle sombras, contornos, degradados o efectos.",
                    "Rehacerlo escribiendo el nombre con otra tipografía: se usan siempre los archivos entregados.",
                    "Ponerlo sobre una foto o un fondo con poco contraste: mejor la versión en negativo o un recuadro claro.",
                    "Invadir su área de respeto con otros textos o imágenes, o recortarlo.",
                    "Usarlo por debajo del tamaño mínimo."]


def _rgb(hexc: str) -> tuple[int, int, int]:
    h = hex_norm(hexc)
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def cmyk_aprox(hexc: str) -> str:
    """CMYK orientativo sin perfil de color: para imprenta, prueba de color con la imprenta."""
    r, g, b = (v / 255 for v in _rgb(hexc))
    k = 1 - max(r, g, b)
    if k >= 1:
        return "C0 M0 Y0 K100"
    c, m, y = ((1 - v - k) / (1 - k) for v in (r, g, b))
    return f"C{round(c * 100)} M{round(m * 100)} Y{round(y * 100)} K{round(k * 100)}"


def _contraste(a: str, b: str) -> float:
    def lum(h):
        def ch(c):
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        r, g, bb = (ch(v) for v in _rgb(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * bb
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


NOMBRES_COLOR = {"primary": "Corporativo", "primary_ink": "Texto sobre el corporativo", "link": "Enlaces", "ink": "Texto",
                 "muted": "Texto secundario", "paper": "Fondo", "surface": "Superficie", "rule": "Líneas"}


def manual_html(root: Path = ROOT, archivos: list[tuple[str, str]] | None = None) -> str:
    cfg = cargar_cfg(root)
    b = dict(cfg["brand"])
    b.setdefault("link", b["primary"])
    static = root / "static"
    mj = root / "marca" / "marca.json"
    m = json.loads(mj.read_text(encoding="utf-8")) if mj.is_file() else {}
    nombre = cfg.get("site_name", "")
    e = html.escape

    def svg_inline(p: Path) -> str:
        t = p.read_text(encoding="utf-8")
        t = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>", "", t)
        return re.sub(r"<svg\b", '<svg aria-hidden="true" focusable="false"', t, count=1)

    logo = static / b["logo"] if b.get("logo") else None
    neg = root / "marca" / "logo-negativo.svg"
    fav = static / "favicon.svg"
    lg = m.get("logo") or {}
    min_px, min_mm = lg.get("tamano_minimo_px", 120), lg.get("tamano_minimo_mm", 30)
    respeto = lg.get("area_respeto", "la mitad de la altura del logo, libre por los cuatro lados")
    claves = [k for k in ("primary", "primary_ink", "link", "ink", "muted", "paper", "surface", "rule") if b.get(k)]
    vistos: dict[str, str] = {}
    for k in claves:
        vistos.setdefault(hex_norm(b[k]), k)
    nombres_m = (m.get("colores") or {}).get("nombres") or {}
    cmyk_m = (m.get("colores") or {}).get("cmyk") or {}
    filas_color = "".join(
        f'<tr><td><span class="sw" style="background:{h}"></span></td><th scope="row">{e(nombres_m.get(k) or NOMBRES_COLOR.get(k, k))}</th>'
        f'<td><code>{h}</code></td><td>{", ".join(map(str, _rgb(h)))}</td><td>{e(cmyk_m.get(k) or cmyk_aprox(h) + " (aprox.)")}</td></tr>'
        for h, k in vistos.items())
    textos = [k for k in ("ink", "muted", "primary", "link", "primary_ink", "paper") if k in b]
    fondos = [k for k in ("paper", "surface", "primary", "ink") if k in b]
    t_uni: dict[str, str] = {}
    for k in textos:
        t_uni.setdefault(hex_norm(b[k]), k)
    f_uni: dict[str, str] = {}
    for k in fondos:
        f_uni.setdefault(hex_norm(b[k]), k)

    def nom(k: str) -> str:
        return e(nombres_m.get(k) or NOMBRES_COLOR.get(k, k))

    def celda(fg: str, bg: str) -> str:
        if fg == bg:
            return '<td class="na">—</td>'
        r = _contraste(fg, bg)
        ratio = f"{r:.1f}:1".replace(".", ",")
        if r >= 4.5:
            return f'<td style="background:{bg};color:{fg}"><span class="aa">Aa</span> {ratio}<br>Texto</td>'
        if r >= 3:
            return f'<td style="background:{bg};color:{fg}"><span class="big">Aa</span><br>{ratio} · solo títulos grandes</td>'
        return f'<td class="no">{ratio}<br>No usar</td>'

    matriz = ("<caption>Filas: color del texto. Columnas: color del fondo.</caption><tr><td></td>"
              + "".join(f'<th scope="col">{nom(k)}<br><code>{bg}</code></th>' for bg, k in f_uni.items()) + "</tr>"
              + "".join(f'<tr><th scope="row">{nom(k)}<br><code>{fg}</code></th>' + "".join(celda(fg, bg) for bg in f_uni) + "</tr>"
                        for fg, k in t_uni.items()))
    lic_por_fam: dict[str, str] = {}
    for f in b.get("font_files") or []:
        lp = static / "fonts" / str(f.get("licencia", ""))
        t = lp.read_text(encoding="utf-8", errors="replace") if lp.is_file() else ""
        lic_por_fam[str(f.get("family", "")).lower()] = next((n for s, n in LICENCIAS if s in t), "revisada a mano" if f.get("licencia_revisada") else "")
    filas_fuente = ""
    for clave, uso in (("font_heading", "Títulos y nombre"), ("font_body", "Textos")):
        fam = (familias(b.get(clave, "")) or ["system-ui"])[0]
        propia = fam.lower() in lic_por_fam
        lic = f"Licencia {lic_por_fam[fam.lower()]}: libre para web, impresos y documentos" if propia else "Del sistema: no hay que instalar nada"
        filas_fuente += (f'<tr><th scope="row">{e(uso)}</th><td><span style="font-family:{e(b.get(clave, ""))};font-size:1.6rem">{e(fam)} · Aa Ññ 123 €</span></td>'
                         f"<td>{e(lic)}</td></tr>")
    tono = m.get("tono") or {}
    tono_html = ""
    if tono:
        lis = []
        if tono.get("trato"):
            lis.append(f"<li>Trato: <strong>{e(tono['trato'])}</strong>.</li>")
        if tono.get("es"):
            lis.append(f"<li>Somos: {e(', '.join(tono['es']))}.</li>")
        if tono.get("no_es"):
            lis.append(f"<li>No somos: {e(', '.join(tono['no_es']))}.</li>")
        if tono.get("palabras_si"):
            lis.append(f"<li>Decimos: {e(', '.join(tono['palabras_si']))}.</li>")
        if tono.get("palabras_no"):
            lis.append(f"<li>Evitamos: {e(', '.join(tono['palabras_no']))}.</li>")
        tono_html = f'<section><h2>Cómo hablamos</h2><ul>{"".join(lis)}</ul></section>'
    neg_html = (f'<figure class="dark" style="background:{b["ink"]}">{svg_inline(neg)}<figcaption>En negativo, sobre fondos oscuros</figcaption></figure>'
                if neg.is_file() else
                '<p class="nota">Sin versión en negativo: sobre fondos oscuros o fotos, el logo va dentro de un recuadro del color de fondo.</p>')
    logo_html = svg_inline(logo) if logo and logo.is_file() else ""
    apps = []
    if fav.is_file():
        apps.append(f'<figure><div class="fav">{svg_inline(fav)}</div><figcaption>Icono de la web (favicon) y base del avatar de redes</figcaption></figure>')
    if (static / "og.png").is_file():
        apps.append(f'<figure><img class="og" src="{_data_url(static / "og.png")}" alt="Imagen que se ve al compartir la web: el logo de {e(nombre)}"><figcaption>Al compartir la web (1200×630)</figcaption></figure>')
    archivos_html = ("<section><h2>Archivos entregados</h2><div class=\"tabla\" tabindex=\"0\" role=\"region\" aria-label=\"Archivos entregados\"><table><thead><tr><th scope=\"col\">Archivo</th><th scope=\"col\">Para qué</th></tr></thead><tbody>"
                     + "".join(f"<tr><td><code>{e(a)}</code></td><td>{e(u)}</td></tr>" for a, u in archivos) + "</tbody></table></div></section>") if archivos else ""
    usos = m.get("usos_incorrectos") or USOS_INCORRECTOS
    lema = f'<p class="lema">{e(m["lema"])}</p>' if m.get("lema") else ""
    hoy = dt.date.today()
    fecha = f"{hoy.day:02d}/{hoy.month:02d}/{hoy.year}"
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manual de marca · {e(nombre)}</title>
<style>{_font_faces(b, static)}
:root{{--ink:{b['ink']};--muted:{b['muted']};--paper:{b['paper']};--surface:{b['surface']};--rule:{b['rule']};--primary:{b['primary']};--radius:{b.get('radius', '8px')}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:{b['font_body']};line-height:1.55;font-size:16px}}
main{{max-width:60rem;margin:0 auto;padding:2rem clamp(1rem,4vw,2.5rem) 3rem}}
h1,h2,h3{{font-family:{b['font_heading']};line-height:1.15}}
h1{{font-size:2.4rem;margin:.5rem 0 .25rem}} h2{{font-size:1.6rem;margin:2.5rem 0 1rem;padding-top:1rem;border-top:3px solid var(--primary)}}
.portada .logo svg{{max-width:min(28rem,100%);height:auto;display:block}}
.lema{{font-size:1.25rem;color:var(--muted)}} .nota{{color:var(--muted)}}
figure{{margin:0;padding:1.5rem;border:1px solid var(--rule);border-radius:var(--radius);background:var(--surface)}}
figure svg{{max-width:100%;height:auto;max-height:7rem;display:block}}
figure.dark{{border-color:transparent}} figure.dark figcaption{{color:{b['paper']}}}
figcaption{{margin-top:.75rem;color:var(--muted);font-size:.95rem}}
.grid{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr))}}
.respeto{{display:inline-block;max-width:100%;padding:2.5rem;outline:2px dashed var(--muted);outline-offset:-2px;background:var(--surface)}}
.respeto svg{{display:block;height:5rem;width:auto;max-width:100%}}
caption{{text-align:left;color:var(--muted);padding-bottom:.4rem}}
.fav svg{{width:6rem;height:6rem}} img.og{{max-width:100%;height:auto;display:block;border-radius:var(--radius)}}
table{{border-collapse:collapse;width:100%;margin:.5rem 0}} th,td{{border:1px solid var(--rule);padding:.5rem .6rem;text-align:left;vertical-align:middle}}
thead th,th[scope=col]{{background:var(--surface)}}
.tabla{{overflow-x:auto}} .tabla:focus-visible{{outline:3px solid var(--primary);outline-offset:2px}} .sw{{display:inline-block;width:2.5rem;height:2.5rem;border-radius:var(--radius);border:1px solid var(--rule)}}
.aa{{font-weight:700;font-size:1.25rem}} .big{{font-weight:700;font-size:1.6rem}}
td.no,td.na{{background:var(--surface);color:var(--ink)}}
code{{font-size:.95em}}
@media print{{@page{{size:A4;margin:14mm}} body{{background:#fff}} main{{padding:0}} h2{{break-after:avoid}} section,figure,table{{break-inside:avoid}}}}
</style></head>
<body><main>
<header class="portada"><div class="logo">{logo_html}</div><h1>Manual de marca de {e(nombre)}</h1>{lema}<p class="nota">Versión del {fecha}</p></header>
<section><h2>Logotipo</h2>
<div class="grid"><figure>{logo_html}<figcaption>Versión principal, sobre fondos claros</figcaption></figure>{neg_html}</div>
<h3>Área de respeto y tamaño mínimo</h3>
<p>Alrededor del logo se deja libre {e(respeto)}. El recuadro discontinuo marca ese espacio:</p>
<p><span class="respeto">{logo_html}</span></p>
<p>Tamaño mínimo: <strong>{min_px} px</strong> de ancho en pantalla y <strong>{min_mm} mm</strong> en papel. Más pequeño no se lee.</p>
</section>
<section><h2>Colores</h2><div class="tabla" tabindex="0" role="region" aria-label="Tabla de colores"><table><thead><tr><th scope="col">Muestra</th><th scope="col">Nombre</th><th scope="col">HEX (web)</th><th scope="col">RGB (pantalla)</th><th scope="col">CMYK (imprenta)</th></tr></thead>
<tbody>{filas_color}</tbody></table></div>
<p class="nota">El CMYK marcado como «aprox.» está calculado sin perfil de color: antes de imprimir mucho, pedir a la imprenta una prueba de color.</p>
<h3>Combinaciones de texto y fondo</h3>
<p>Con estas combinaciones el texto se lee bien (contraste mínimo de 4,5:1, nivel AA de las pautas WCAG); las de 3:1 solo valen para títulos grandes.</p>
<div class="tabla" tabindex="0" role="region" aria-label="Combinaciones de texto y fondo"><table>{matriz}</table></div></section>
<section><h2>Tipografías</h2><div class="tabla" tabindex="0" role="region" aria-label="Tabla de tipografías"><table><thead><tr><th scope="col">Uso</th><th scope="col">Familia</th><th scope="col">Licencia</th></tr></thead><tbody>{filas_fuente}</tbody></table></div>
<p class="nota">Las fuentes para instalar en el ordenador (Word, Canva, programas de diseño) van en la carpeta <code>fuentes/</code> con su licencia.</p></section>
{tono_html}
<section><h2>Usos incorrectos</h2><ul>{"".join(f"<li>{e(u)}</li>" for u in usos)}</ul></section>
{f'<section><h2>Aplicaciones</h2><div class="grid">{"".join(apps)}</div></section>' if apps else ""}
{archivos_html}
</main></body></html>
"""


def _png_de_svg(nav: Navegador, svg: Path, ancho: int, out: Path, fondo: str | None = None, alto: int | None = None, margen: float = 0.0) -> None:
    vb = viewbox(svg.read_text(encoding="utf-8"))
    alto = alto or round(ancho * vb[3] / vb[2])
    inner_w, inner_h = ancho * (1 - 2 * margen), alto * (1 - 2 * margen)
    page = nav.pagina(ancho, alto)
    page.set_content(f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>png</title><style>html,body{{margin:0;width:{ancho}px;height:{alto}px;'
                     f'background:{fondo or "transparent"};display:flex;align-items:center;justify-content:center}}'
                     f'img{{width:{inner_w}px;height:{inner_h}px;object-fit:contain}}</style></head><body><img src="{_data_url(svg)}" alt=""></body></html>',
                     wait_until="load")
    page.screenshot(path=str(out), omit_background=fondo is None, clip={"x": 0, "y": 0, "width": ancho, "height": alto})
    page.context.close()


def _pdf_de_svg(nav: Navegador, svg: Path, out: Path, ancho_mm: int = 100) -> None:
    t = svg.read_text(encoding="utf-8")
    vb = viewbox(t)
    alto_mm = ancho_mm * vb[3] / vb[2]
    page = nav.pagina(800, 600)
    page.set_content(f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>pdf</title><style>@page{{size:{ancho_mm}mm {alto_mm:.2f}mm;margin:0}}'
                     f'html,body{{margin:0}} svg{{width:{ancho_mm}mm;height:{alto_mm:.2f}mm;display:block}}</style></head><body>{t}</body></html>', wait_until="load")
    page.pdf(path=str(out), width=f"{ancho_mm}mm", height=f"{alto_mm:.2f}mm", print_background=False)
    page.context.close()


def _pesos_escritorio(f: dict) -> list[int]:
    """Regular y Bold de una variable (dentro de su rango); el peso de una estática."""
    nums = [int(float(x)) for x in str(f.get("weight", "400")).split()]
    if len(nums) == 2:
        lo, hi = nums
        return sorted({min(max(400, lo), hi), min(max(700, lo), hi)})
    return nums[:1] or [400]


def _estatica(path: Path, peso: int, familia: str, estilo: str):
    """woff2 → TTF fijo en un peso, con nombres limpios (familia + Regular/Bold): Word y Canva lo agrupan bien al instalarlo."""
    from fontTools.ttLib import TTFont

    ft = TTFont(path)
    if "fvar" in ft:
        from fontTools.varLib import instancer

        ejes = {a.axisTag: a for a in ft["fvar"].axes}
        lim: dict[str, float | None] = {k: None for k in ejes}
        if "wght" in ejes:
            lim["wght"] = min(max(peso, ejes["wght"].minValue), ejes["wght"].maxValue)
        ft = instancer.instantiateVariableFont(ft, lim)
    ft.flavor = None  # woff2 solo sirve en la web; TTF se instala en Windows y macOS
    bold, italic = estilo.startswith("Bold"), estilo.endswith("Italic")
    name = ft["name"]
    for nid in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
        name.removeNames(nameID=nid)
    ps = f"{familia}-{estilo}".replace(" ", "")
    for nid, val in ((1, familia), (2, estilo), (3, f"{ps};kit-de-marca"), (4, f"{familia} {estilo}"), (6, ps)):
        name.setName(val, nid, 3, 1, 0x409)
    os2 = ft["OS/2"]
    os2.usWeightClass = 700 if bold else 400
    os2.fsSelection = (os2.fsSelection & ~(1 | 32 | 64)) | (32 if bold else 0) | (1 if italic else 0) | (64 if not (bold or italic) else 0)
    ft["head"].macStyle = (ft["head"].macStyle & ~3) | (1 if bold else 0) | (2 if italic else 0)
    return ft


def kit_problemas(root: Path = ROOT) -> list[str]:
    """Lo que impide entregar la marca: los errores de `revisar`, el contraste de la paleta y datos pendientes en marca/marca.json."""
    cfg = cargar_cfg(root)
    errs, _ = revisar(root)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import brand as brand_mod
    finally:
        sys.path.pop(0)
    b = dict(cfg["brand"])
    b.setdefault("link", b["primary"])
    b.setdefault("focus", b["primary"])
    for pares, minimo in ((brand_mod.PAIRS, brand_mod.MIN), (brand_mod.NONTEXT, brand_mod.MIN_NONTEXT)):
        for fg, bg, uso in pares:
            r = brand_mod.contrast(b[fg], b[bg])
            if r < minimo:
                errs.append(f"contraste {r:.2f}:1 en {uso} ({fg} sobre {bg}): python tools/brand.py --fix")
    if not b.get("logo"):
        errs.append("falta brand.logo")
    neg = root / "marca" / "logo-negativo.svg"
    if neg.is_file():
        e, _ = svg_problemas(neg.read_text(encoding="utf-8"), "logo", paleta(cfg["brand"]))
        errs += [f"marca/logo-negativo.svg: {x}" for x in e]
    mj = root / "marca" / "marca.json"
    if mj.is_file():
        t = mj.read_text(encoding="utf-8")
        try:
            json.loads(t)
        except ValueError as ex:
            errs.append(f"marca/marca.json: JSON no válido ({ex})")
        if "[CONFIRMAR" in t:
            errs.append("marca/marca.json: queda algún [CONFIRMAR]")
    return errs


def kit(root: Path = ROOT, nav: Navegador | None = None) -> Path:
    """marca/entrega/ y marca/entrega-<web>-<fecha>.zip. Se para si algo de la marca falla (no se entrega una marca rota)."""
    errs = kit_problemas(root)
    if errs:
        raise SystemExit("ERROR: no se genera el kit:\n  " + "\n  ".join(errs))
    if not hay_fonttools():
        raise SystemExit("ERROR: el kit necesita fontTools y brotli (pip install fonttools==4.66.1 brotli==1.2.0) para las fuentes de escritorio")
    cfg = cargar_cfg(root)
    b = cfg["brand"]
    static = root / "static"
    out = root / "marca" / "entrega"
    if out.exists():
        shutil.rmtree(out)
    (out / "logo").mkdir(parents=True)
    archivos: list[tuple[str, str]] = []
    propio = nav is None
    nav = nav or Navegador().__enter__()
    try:
        versiones = [("logo", static / b["logo"], "principal")]
        if (root / "marca" / "logo-negativo.svg").is_file():
            versiones.append(("logo-negativo", root / "marca" / "logo-negativo.svg", "en negativo, para fondos oscuros"))
        for nombre, src, que in versiones:
            if src.suffix.lower() != ".svg":
                raise SystemExit(f"ERROR: el kit necesita el logo en SVG ({src.name})")
            shutil.copy(src, out / "logo" / f"{nombre}.svg")
            archivos.append((f"logo/{nombre}.svg", f"Logo {que}. Vectorial (SVG): web, rótulos y cualquier tamaño"))
            _pdf_de_svg(nav, src, out / "logo" / f"{nombre}.pdf")
            archivos.append((f"logo/{nombre}.pdf", f"Logo {que}. Vectorial (PDF): imprenta y programas de diseño"))
            for w in (600, 1200):
                _png_de_svg(nav, src, w, out / "logo" / f"{nombre}-{w}.png")
                archivos.append((f"logo/{nombre}-{w}.png", f"Logo {que}. PNG de {w} px con fondo transparente: documentos, presentaciones, Canva"))
        fav = static / "favicon.svg"
        if fav.is_file():
            shutil.copy(fav, out / "favicon.svg")
            archivos.append(("favicon.svg", "Icono de la web (pestaña del navegador)"))
            (out / "redes").mkdir()
            _png_de_svg(nav, fav, 1080, out / "redes" / "avatar-1080.png", fondo=b["paper"], alto=1080, margen=0.16)
            archivos.append(("redes/avatar-1080.png", "Foto de perfil de redes, WhatsApp Business y Google: el icono dentro del círculo que recortan"))
        if (static / "og.png").is_file():
            (out / "redes").mkdir(exist_ok=True)
            shutil.copy(static / "og.png", out / "redes" / "compartir-1200x630.png")
            archivos.append(("redes/compartir-1200x630.png", "Imagen que sale al compartir la web en WhatsApp y redes"))
        fuentes = [f for f in b.get("font_files") or [] if (static / "fonts" / str(f.get("file", ""))).is_file()]
        hechas: set[tuple[str, str]] = set()
        for f in fuentes:
            lic = str(f.get("licencia") or "")
            lic_txt = (static / "fonts" / lic).read_text(encoding="utf-8", errors="replace") if lic and (static / "fonts" / lic).is_file() else ""
            (out / "fuentes").mkdir(exist_ok=True)
            if lic and not (out / "fuentes" / lic).exists():
                shutil.copy(static / "fonts" / lic, out / "fuentes" / lic)
                archivos.append((f"fuentes/{lic}", f"Licencia de {f['family']}: va siempre con la fuente"))
            if re.search(r"with Reserved Font Name", lic_txt, re.I):
                # Con nombre reservado, una versión recortada o fija no puede llamarse igual (OFL): se descarga la original de su autor.
                archivos.append((f"fuentes/{f['family']}", f"Descargar la familia completa de su web oficial ({f.get('origen', 'ver la licencia')}): su licencia reserva el nombre"))
                continue
            for peso in _pesos_escritorio(f):
                estilo = ("Bold" if peso >= 600 else "Regular") + (" Italic" if f.get("style") == "italic" else "")
                if (f["family"], estilo) in hechas:
                    continue
                hechas.add((f["family"], estilo))
                ttf = f"{f['family'].replace(' ', '')}-{estilo.replace(' ', '')}.ttf"
                _estatica(static / "fonts" / f["file"], peso, f["family"], estilo).save(out / "fuentes" / ttf)
                archivos.append((f"fuentes/{ttf}", f"Fuente {f['family']} {estilo} para instalar en el ordenador (Word, Canva, diseño); "
                                                   "con los caracteres de la web"))
        archivos += [("manual.html", "Manual de marca (se abre en el navegador)"), ("manual.pdf", "Manual de marca para imprimir o enviar")]
        man = manual_html(root, archivos)
        (out / "manual.html").write_text(man, encoding="utf-8")
        page = nav.pagina(1000, 1400)
        page.set_content(man, wait_until="load")
        page.evaluate("document.fonts.ready.then(() => true)")
        page.pdf(path=str(out / "manual.pdf"), format="A4", print_background=True, margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"})
        page.context.close()
    finally:
        if propio:
            nav.__exit__(None, None, None)
    leeme = [f"Identidad de marca de {cfg.get('site_name', '')} · {dt.date.today().isoformat()}", ""]
    leeme += [f"{a}\n    {u}" for a, u in archivos]
    leeme += ["", "Los logos y el manual son de quien figure como titular en el contrato. Las fuentes tienen su propia licencia (carpeta fuentes/)."]
    (out / "LEEME.txt").write_text("\n".join(leeme) + "\n", encoding="utf-8")
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", cfg.get("site_name", "marca")).encode("ascii", "ignore").decode().lower()).strip("-")
    zp = root / "marca" / f"entrega-{slug or 'marca'}-{dt.date.today().isoformat()}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out))
    return zp


# ---------------------------------------------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("revisar")
    p = sub.add_parser("fuente")
    p.add_argument("id")
    p.add_argument("--version", default="")
    p.add_argument("--estatica", action="store_true")
    p.add_argument("--pesos", default="")
    p.add_argument("--italica", action="store_true")
    p.add_argument("--subconjunto", default="latin")
    p.add_argument("--paquete-local", default="", help=argparse.SUPPRESS)
    p = sub.add_parser("logotipo")
    p.add_argument("texto")
    p.add_argument("--fuente", required=True)
    p.add_argument("--peso", type=float)
    p.add_argument("--eje", action="append", default=[], help="TAG=VALOR, p. ej. opsz=72")
    p.add_argument("--simbolo", default="")
    p.add_argument("--color", default="")
    p.add_argument("--espaciado", type=float, default=0.0, help="en em: 0.05 abre las letras (útil en mayúsculas)")
    p.add_argument("--altura-simbolo", type=float, default=1.6)
    p.add_argument("--salida", default="static/img/logo.svg")
    p = sub.add_parser("og")
    p.add_argument("--foto", default="")
    p.add_argument("--texto", default="")
    sub.add_parser("kit")
    a = ap.parse_args(argv)
    if a.cmd == "revisar":
        errs, warns = revisar(ROOT)
        for w in warns:
            print("AVISO:", w)
        for e in errs:
            print("ERROR:", e)
        print(f"Marca: {len(errs)} errores · {len(warns)} avisos (los caracteres de las fuentes los mira check.py sobre public/)")
        return 1 if errs else 0
    if a.cmd == "fuente":
        pesos = [int(x) for x in a.pesos.split(",") if x.strip()] if a.pesos else None
        entradas = fuente(a.id, version=a.version, estatica=a.estatica, pesos=pesos, italica=a.italica, subconjunto=a.subconjunto,
                          tgz=Path(a.paquete_local) if a.paquete_local else None)
        print("Copiado a static/fonts/ (woff2 y licencia). Añadir a site.json > brand.font_files:")
        print(json.dumps(entradas, ensure_ascii=False, indent=2))
        print(f"y en font_heading o font_body: \"'{entradas[0]['family']}', <familia del sistema>, serif|sans-serif\"")
        return 0
    if a.cmd == "logotipo":
        if not hay_fonttools():
            raise SystemExit("ERROR: pip install fonttools==4.66.1 brotli==1.2.0")
        ejes = {}
        for kv in a.eje:
            k, _, v = kv.partition("=")
            ejes[k.strip()] = float(v)
        color = a.color or cargar_cfg()["brand"]["ink"]
        svg = logotipo(a.texto, Path(a.fuente), peso=a.peso, ejes=ejes, color=color, simbolo=Path(a.simbolo) if a.simbolo else None,
                       espaciado=a.espaciado, altura_simbolo=a.altura_simbolo)
        out = Path(a.salida)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg, encoding="utf-8")
        e, w = svg_problemas(svg, "logo")
        vb = viewbox(svg)
        print(f"{out}: {vb[2]:g}×{vb[3]:g}, {len(svg.encode()) // 1024 + 1} KB, en trazos" + ("" if not (e or w) else f" · {'; '.join(e + w)}"))
        return 1 if e else 0
    if a.cmd == "og":
        out = og(ROOT, Path(a.foto) if a.foto else None, a.texto)
        print(f"{out}: 1200×630")
        return 0
    zp = kit(ROOT)
    print(f"Kit de marca: {zp.relative_to(ROOT)} (y la carpeta marca/entrega/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
