#!/usr/bin/env python3
"""Importa una exportación de WordPress (WXR: Herramientas > Exportar > Todo el contenido) a Markdown de la plantilla A.

    python tools/importar_wordpress.py exportacion.xml [--lang es] [--salida migracion] [--sobrescribir]

También sirve para webs de Squarespace (exportan en formato de WordPress) y de cualquier plataforma que exporte WXR.
Escribe en `migracion/` (no en content/: nada se publica sin revisarlo):
- `blog/<slug>.md` (entradas) y `paginas/<slug>.md` (páginas): con la cabecera de la plantilla, listas para revisar y mover a
  content/<idioma>/blog/ o content/<idioma>/;
- `redirecciones.json`: dirección antigua → nueva, para copiar a site.json > redirecciones.reglas (las de ?p=123 solo con .htaccess);
- `imagenes.csv`: imágenes del contenido (dirección original → ruta nueva), para descargarlas y pasarlas por tools/images.py;
- `informe.md`: qué se ha importado, qué no y qué hay que revisar a mano (formularios, vídeos, códigos cortos, textos alternativos).

Seguridad y privacidad:
- solo se importa lo publicado: borradores, privadas, programadas, con contraseña y la papelera se quedan fuera;
- nunca comentarios, autores ni emails (datos personales que no hacen falta en la web nueva);
- el resultado es Markdown sin HTML: scripts, iframes, formularios, estilos y atributos (onclick…) no pasan;
- se rechaza un XML con DOCTYPE o entidades propias (un WXR normal no los lleva).
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {"content": "http://purl.org/rss/1.0/modules/content/", "excerpt": "http://wordpress.org/export/1.2/excerpt/"}
BLOG_SLUG = {"es": "blog", "en": "blog"}  # mismas rutas que SLUGS de build.py
DROP = {"script", "style", "iframe", "object", "embed", "form", "input", "button", "select", "textarea", "noscript", "svg", "video",
        "audio", "canvas", "template", "link", "meta", "head", "title"}
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "col", "area", "embed", "param", "track"}
EMBEDS = [(r"youtube\.com|youtu\.be", "Ver el vídeo en YouTube"), (r"vimeo\.com", "Ver el vídeo en Vimeo"),
          (r"google\.[a-z.]+/maps|maps\.google|goo\.gl/maps", "Ver en Google Maps")]
ALT_PENDIENTE = "[CONFIRMAR: texto alternativo de la imagen {}]"
# Páginas que genera la plantilla (site.json): la de WordPress no se publica tal cual y su dirección ya existe en la web nueva.
PROPIAS = ("blog", "aviso-legal", "privacidad", "accesibilidad", "gracias", "politica-cookies", "home")
# Lo que deja una instalación nueva de WordPress (en inglés y en español) y las páginas de sistema de WooCommerce.
EJEMPLO = {("post", "hello-world"), ("post", "hola-mundo"), ("page", "sample-page"), ("page", "pagina-ejemplo"), ("page", "pagina-de-ejemplo")}
EJEMPLO_TEXTO = re.compile(r"Welcome to WordPress|Bienvenido a WordPress|This is an example page|Esta es una página de ejemplo", re.I)
WOO_SISTEMA = re.compile(r"<!--\s*wp:woocommerce/(?:cart|checkout|classic-shortcode|customer-account|order-confirmation)\b"
                         r"|\[woocommerce_(?:cart|checkout|my_account|order_tracking)\b", re.I)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", unquote(value)).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[\s_-]+", "-", value).strip("-")[:80]


def esc_text(s: str) -> str:
    """Texto literal en Markdown: sin HTML (lo que era &lt;script&gt; se queda en texto), sin marcas y sin bloques :::."""
    s = s.replace("\\", "\\\\").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"([*_`\[\]])", r"\\\1", s)
    return s.replace(":::", "&#58;::")


def safe_href(href: str, base: str) -> str | None:
    href = (href or "").strip()
    if not href or href.startswith("#"):
        return href or None
    low = href.lower()
    if low.startswith(("mailto:", "tel:")):
        return quote(href, safe=":@+.-_~%")
    u = urljoin(base + "/", href) if base else href
    if not u.lower().startswith(("http://", "https://")):
        return None  # javascript:, data:, vbscript:…
    return quote(u, safe=":/?#[]@!$&'*+,;=%-._~")


class ToMarkdown(HTMLParser):
    """HTML del contenido de WordPress → Markdown. Solo lo que la plantilla sabe mostrar; lo demás, a la lista de revisar."""

    def __init__(self, base: str, links: dict[str, str], images: list[tuple[str, str]], notes: list[str], img_dir: str):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self.images, self.notes, self.img_dir = base, links, images, notes, img_dir
        self.out: list[str] = []
        self.stack: list[str] = []
        self.drop = 0
        self.href: list[str | None] = []
        self.lists: list[list] = []  # [tipo, contador]
        self.table: list[list[str]] | None = None
        self.cell: list[str] | None = None
        self.pre = 0
        self.heading_shift: int | None = None
        self.last_level = 1

    # -- utilidades
    def w(self, s: str):
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.out.append(s)

    def block(self):
        self.w("\n\n")

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in VOID and tag not in ("br", "img", "hr", "embed"):
            return
        if self.drop:
            if tag not in VOID:
                self.drop += 1
            return
        if tag in DROP:
            if tag == "iframe" or tag == "embed":
                src = a.get("src", "")
                for rx, label in EMBEDS:
                    if re.search(rx, src, re.I):
                        m = re.search(r"youtube(?:-nocookie)?\.com/embed/([\w-]{6,20})", src)
                        h = f"https://www.youtube.com/watch?v={m.group(1)}" if m else safe_href(src, self.base)
                        if h:
                            self.block()
                            self.w(f"[{label}]({h})")
                            self.block()
                            self.notes.append(f"vídeo o mapa incrustado → enlace ({label}); poner una imagen propia que enlace (sin cargar el tercero)")
                        break
                else:
                    self.notes.append(f"<{tag}> quitado ({src[:80] or 'sin src'}): revisar si hacía falta")
            elif tag in ("form", "input", "button", "select", "textarea"):
                self.notes.append(f"formulario quitado: usar el bloque :::contact de la plantilla")
            elif tag == "script":
                self.notes.append("script quitado")
            if tag not in ("embed",):
                self.drop = 1
            return
        if tag in ("p", "div", "section", "article", "figure", "header", "footer", "aside", "main"):
            self.block()
        elif re.fullmatch(r"h[1-6]", tag):
            lv = int(tag[1])
            if self.heading_shift is None:
                self.heading_shift = 2 - lv  # el primer encabezado del contenido pasa a ser h2 (el h1 es el título)
            # Sin saltos de nivel (h2 → h4): el lector de pantalla navega por encabezados.
            lv = min(6, max(2, lv + self.heading_shift), self.last_level + 1)
            self.last_level = lv
            self.block()
            self.w("#" * lv + " ")
        elif tag == "br":
            self.w("  \n" if not self.pre else "\n")
        elif tag == "hr":
            self.block()
            self.w("---")
            self.block()
        elif tag in ("strong", "b"):
            self.w("**")
        elif tag in ("em", "i"):
            self.w("*")
        elif tag == "a":
            h = safe_href(a.get("href", ""), self.base)
            if h and h.split("#")[0] in self.links:
                h = self.links[h.split("#")[0]] + ("#" + h.split("#")[1] if "#" in h else "")
            self.href.append(h)
            if h:
                self.w("[")
        elif tag in ("ul", "ol"):
            self.lists.append([tag, 0])
            self.block()
        elif tag == "li":
            depth = max(0, len(self.lists) - 1)
            kind = self.lists[-1] if self.lists else ["ul", 0]
            kind[1] += 1
            self.w("\n" + "    " * depth + ("1. " if kind[0] == "ol" else "- "))
        elif tag == "blockquote":
            self.block()
            self.w("> ")
        elif tag == "img":
            src = a.get("src", "")
            u = safe_href(src, self.base)
            if not u:
                return
            name = slugify(Path(urlparse(u).path).stem) or f"imagen-{len(self.images) + 1}"
            name = re.sub(r"-\d+x\d+$", "", name)  # miniaturas de WordPress: foto-1024x768.jpg → foto
            new = f"/{self.img_dir}/{name}.webp"
            self.images.append((u, new))
            alt = " ".join(a.get("alt", "").split())
            self.w(f"![{esc_text(alt)}]({new})")
            if not alt:
                # Visible a propósito: check.py --release falla hasta que alguien describa la imagen (o la marque como decorativa).
                self.w(f"\n\n{esc_text(ALT_PENDIENTE.format(name))}\n\n")
                self.notes.append(f"imagen sin texto alternativo: {name}")
        elif tag == "figcaption":
            self.block()
            self.w("*")
        elif tag in ("pre",):
            self.pre += 1
            self.block()
            self.w("```\n")
        elif tag == "code" and not self.pre:
            self.w("`")
        elif tag == "table":
            self.table = []
            self.block()
        elif tag == "tr" and self.table is not None:
            self.table.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if self.drop:
            if tag not in VOID:
                self.drop -= 1
            return
        if tag in ("p", "div", "section", "article", "figure", "header", "footer", "aside", "main", "blockquote") or re.fullmatch(r"h[1-6]", tag):
            self.block()
        elif tag in ("strong", "b"):
            self.w("**")
        elif tag in ("em", "i"):
            self.w("*")
        elif tag == "a":
            h = self.href.pop() if self.href else None
            if h:
                self.w(f"]({h})")
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self.block()
        elif tag == "figcaption":
            self.w("*")
            self.block()
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.w("\n```")
            self.block()
        elif tag == "code" and not self.pre:
            self.w("`")
        elif tag in ("td", "th") and self.table is not None and self.cell is not None:
            txt = " ".join("".join(self.cell).split()).replace("|", "\\|")
            if self.table:
                self.table[-1].append(txt)
            self.cell = None
        elif tag == "table" and self.table is not None:
            rows = [r for r in self.table if r]
            self.table = None
            if rows:
                n = max(len(r) for r in rows)
                rows = [r + [""] * (n - len(r)) for r in rows]
                self.w("| " + " | ".join(rows[0]) + " |\n|" + "---|" * n + "\n")
                self.w("".join("| " + " | ".join(r) + " |\n" for r in rows[1:]))
                self.notes.append("tabla convertida: revisar que la primera fila son los encabezados")
            self.block()

    def handle_data(self, data):
        if self.drop:
            return
        if self.pre:
            self.w(data.replace("```", "ˋˋˋ"))
            return
        if self.table is not None and self.cell is None:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip() or (self.out and not self.out[-1].endswith((" ", "\n"))):
            t = esc_text(text)
            if self.at_line_start():
                # Que un texto que empieza por «1984.», «- » o «# » no se convierta en lista o encabezado.
                t = re.sub(r"^(\s*)(\d+)\.(\s)", r"\1\2\\.\3", t)
                t = re.sub(r"^(\s*)([-+#>])", r"\1\\\2", t)
            self.w(t)

    def at_line_start(self) -> bool:
        prev = "".join(self.cell if self.cell is not None else self.out[-3:])
        return prev == "" or prev.endswith("\n")

    def handle_comment(self, data):
        pass  # comentarios de bloques de Gutenberg (<!-- wp:paragraph -->) y cualquier otro

    def markdown(self) -> str:
        txt = "".join(self.out)
        txt = re.sub(r"[ \t]+\n", lambda m: "  \n" if m.group(0).startswith("  ") else "\n", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        return "\n".join(l.rstrip() if not l.endswith("  ") else l for l in txt.strip().splitlines()) + "\n"


SHORTCODE = re.compile(r"\[(/?)([a-zA-Z][\w-]*)([^\]]*)\]")


def strip_shortcodes(content: str, notes: list[str]) -> str:
    def rep(m):
        name = m.group(2).lower()
        if name in ("caption", "embed"):
            return ""  # se queda lo de dentro (la imagen o el enlace)
        if not m.group(1):
            notes.append(f"código corto [{name}] quitado: revisar qué mostraba")
        return ""
    return SHORTCODE.sub(rep, content)


def autop(content: str) -> str:
    """WordPress guarda los párrafos como saltos de línea dobles (wpautop): se convierten en <p> si el contenido no los trae."""
    if re.search(r"<p[\s>]", content, re.I):
        return content
    return "".join(f"<p>{p}</p>" for p in re.split(r"\n\s*\n", content) if p.strip())


def front(meta: dict) -> str:
    lines = ["---"]
    for k, v in meta.items():
        v = " ".join(str(v).split())
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}" if k != "date" else f"{k}: {v}")
    return "\n".join(lines) + "\n---\n\n"


def summary_text(md: str, n: int = 155) -> str:
    """Descripción a partir de los párrafos de texto (sin encabezados, imágenes, listas ni tablas)."""
    paras = [p for p in md.split("\n\n") if p.strip() and not re.match(r"\s*(?:#|!\[|\||- |\d+\. |> |```|\\\[CONFIRMAR|---\s*$|\[[^\]]*\]\([^)]*\)\s*$)", p)]
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)|\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(paras))
    t = re.sub(r"(?<!\\)[*_`]", "", t)
    t = html.unescape(re.sub(r"\\(.)", r"\1", t))
    t = " ".join(t.split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def incrustados(md: str, notes: list[str]) -> str:
    """Una dirección sola en su párrafo es un vídeo o mapa incrustado (bloque «Insertar» o el autoembed del editor clásico): pasa a enlace."""
    def rep(m):
        url = m.group(1).replace("\\", "")
        for rx, label in EMBEDS:
            if re.search(rx, url, re.I):
                notes.append(f"vídeo o mapa incrustado → enlace ({label}); poner una imagen propia que enlace (sin cargar el tercero)")
                return f"[{label}]({url})"
        return m.group(0)
    return re.sub(r"(?m)^(https?://\S+)$", rep, md)


def parse_wxr(raw: bytes) -> ET.Element:
    head = raw[:4096].decode("utf-8", "replace").upper()
    if "<!DOCTYPE" in head or b"<!ENTITY" in raw.upper():
        raise ValueError("el XML trae DOCTYPE o entidades propias: un WXR de WordPress no los lleva; no se importa")
    return ET.fromstring(raw)


def run(xml_path: Path, out: Path, lang: str = "es", overwrite: bool = False) -> dict:
    root = parse_wxr(xml_path.read_bytes())
    ch = root.find("channel")
    if ch is None:
        raise ValueError("no es una exportación de WordPress (falta <channel>)")
    wpns = next((t[1:].split("}")[0] for t in (e.tag for e in ch.iter()) if t.startswith("{http://wordpress.org/export/")), "http://wordpress.org/export/1.2/")
    q = lambda e, name: (e.findtext(f"{{{wpns}}}{name}") or "").strip()  # noqa: E731
    base = (q(ch, "base_blog_url") or ch.findtext("link") or "").rstrip("/")
    if out.exists() and any(out.iterdir()) and not overwrite:
        raise ValueError(f"{out} ya tiene archivos: revisarlos y borrarlos, o usar --sobrescribir")
    if overwrite and out.exists():
        # Lo generado por una importación anterior: si no, quedarían páginas que esta vez se dejan fuera (ensayo general).
        for f in [*out.glob("blog/*.md"), *out.glob("paginas/*.md"), out / "imagenes.csv", out / "redirecciones.json", out / "informe.md"]:
            f.unlink(missing_ok=True)
    items = ch.findall("item")
    stats: dict[str, int] = {}
    chosen, skipped = [], []
    used: set[str] = set()
    avisos_previos: dict[str, list[str]] = {}
    prefix = "/" if lang == "es" else f"/{lang}/"
    for it in items:
        ptype, status = q(it, "post_type"), q(it, "status")
        title = html.unescape(it.findtext("title") or "").strip()
        if ptype not in ("post", "page"):
            stats[f"tipo {ptype or '?'} (no se importa)"] = stats.get(f"tipo {ptype or '?'} (no se importa)", 0) + 1
            continue
        if status != "publish" or q(it, "post_password"):
            why = "con contraseña" if q(it, "post_password") else status or "sin estado"
            skipped.append(f"{'entrada' if ptype == 'post' else 'página'} «{title[:60]}» ({why})")
            continue
        slug = slugify(q(it, "post_name")) or slugify(title) or f"{ptype}-{q(it, 'post_id')}"
        content = it.findtext("content:encoded", namespaces=NS) or ""
        tipo = "entrada" if ptype == "post" else "página"
        if (ptype, slug) in EJEMPLO and (EJEMPLO_TEXTO.search(content) or not content.strip()):
            skipped.append(f"{tipo} «{title[:60]}» (contenido de ejemplo de WordPress)")
            continue
        if ptype == "page" and (WOO_SISTEMA.search(content) or (slug in ("shop", "tienda") and not re.sub(r"<!--.*?-->|\s", "", content, flags=re.S))):
            skipped.append(f"página «{title[:60]}» (de sistema de WooCommerce: la tienda nueva tiene la suya; si tenía visitas, "
                           f"redirigir /{slug}/ a mano a la página equivalente)")
            continue
        s, n = slug, 2
        while s in used or s in PROPIAS:
            s, n = f"{slug}-{n}", n + 1
        used.add(s)
        portada = ptype == "page" and base and (it.findtext("link") or "").strip().rstrip("/") == base
        new = (f"{prefix}{BLOG_SLUG.get(lang, 'blog')}/{s}/" if ptype == "post" else prefix if portada else f"{prefix}{s}/")
        chosen.append((it, ptype, s, title, new))
        avisos_previos[s] = ([f"era la portada: su contenido va a content/{lang}/home.md (no como página aparte); los enlaces a ella ya apuntan a {prefix}"]
                             if portada else [f"la plantilla ya tiene /{slug}/ (se genera desde site.json): pasar a site.json lo que falte "
                                              "y no publicar esta página; esa dirección no necesita redirección"] if slug in PROPIAS else [])
    # Enlaces internos: direcciones antiguas → nuevas (para reescribir los enlaces dentro del contenido y para las redirecciones).
    links: dict[str, str] = {}
    redirs: dict[str, str] = {}
    only_ht: dict[str, str] = {}
    for it, ptype, s, title, new in chosen:
        for old in {it.findtext("link") or "", it.findtext("guid") or ""}:
            old = old.strip()
            if not old:
                continue
            u = urlparse(old)
            if base and u.netloc and u.netloc != urlparse(base).netloc:
                continue
            links[quote(old, safe=":/?#[]@!$&'*+,;=%-._~")] = new
            path = quote(unquote(u.path or "/"), safe="/%-._~") or "/"
            if u.query:
                if re.fullmatch(r"(?:p|page_id)=\d+", u.query):
                    only_ht[f"{path}?{u.query}"] = new
            elif path not in ("/", new) and path.rstrip("/") != new.rstrip("/") and path.strip("/") not in PROPIAS:
                redirs[path] = new
    blog_dir, page_dir = out / "blog", out / "paginas"
    blog_dir.mkdir(parents=True, exist_ok=True)
    page_dir.mkdir(parents=True, exist_ok=True)
    images: list[tuple[str, str]] = []
    report = []
    for it, ptype, s, title, new in chosen:
        notes: list[str] = list(avisos_previos.get(s, []))
        content = it.findtext("content:encoded", namespaces=NS) or ""
        conv = ToMarkdown(base, links, images, notes, "img/blog" if ptype == "post" else "img/paginas")
        conv.feed(autop(strip_shortcodes(content, notes)))
        conv.close()
        body = incrustados(conv.markdown(), notes)
        excerpt = html.unescape(re.sub(r"<[^>]+>", " ", it.findtext("excerpt:encoded", namespaces=NS) or "")).strip()
        meta = {"key": s, "title": title or s, "description": summary_text(excerpt) if excerpt else summary_text(body)}
        if ptype == "post":
            meta["date"] = (q(it, "post_date") or "")[:10] or "2000-01-01"
        if not meta["description"]:
            meta["description"] = "[CONFIRMAR: descripción de 140-160 caracteres]"
            notes.append("sin descripción: escribirla")
        elif not excerpt and len(meta["description"]) < 70:
            # Sacada de un texto corto («No. Tampoco.»): no sirve como resumen en Google (ensayo con una exportación real).
            meta["description"] = f"[CONFIRMAR: descripción de 140-160 caracteres; el texto empieza «{meta['description']}»]"
            notes.append("descripción demasiado corta: escribirla")
        (blog_dir if ptype == "post" else page_dir).joinpath(f"{s}.md").write_text(front(meta) + body, encoding="utf-8")
        report.append((ptype, s, new, notes))
        stats["entradas" if ptype == "post" else "páginas"] = stats.get("entradas" if ptype == "post" else "páginas", 0) + 1
    seen_img: dict[str, str] = {}
    for orig, new in images:
        seen_img.setdefault(orig, new)
    with (out / "imagenes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")  # sin \r: se lee también con un bucle de la terminal
        w.writerow(["original", "nueva"])
        w.writerows(seen_img.items())
    (out / "redirecciones.json").write_text(json.dumps({
        "_nota": "Copiar «reglas» a site.json > redirecciones.reglas cuando las páginas estén en content/. «solo_htaccess» (direcciones con "
                 "?p=123) solo funcionan con redirecciones.htaccess = true (alojamiento Apache); en GitHub Pages, dejarlas fuera.",
        "reglas": dict(sorted(redirs.items())), "solo_htaccess": dict(sorted(only_ht.items()))}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    L = [f"# Importación de WordPress: {base or xml_path.name}", "", "Resultado en esta carpeta. **Nada está publicado**: revisar cada archivo, "
         "moverlo a content/ y copiar las redirecciones a site.json.", "", "## Importado", ""]
    L += [f"- {k}: {v}" for k, v in sorted(stats.items())] or ["- nada"]
    L += ["", f"- imágenes que descargar: {len(seen_img)} (imagenes.csv → carpeta → `python tools/images.py carpeta/ static/img/blog/`)",
          f"- redirecciones: {len(redirs)} (+ {len(only_ht)} solo con .htaccess)", "", "## No importado (solo lo publicado)", ""]
    L += [f"- {x}" for x in skipped] or ["- nada"]
    L += ["", "- Comentarios, autores y sus emails: nunca se importan (datos personales que la web nueva no necesita).",
          "- Productos de WooCommerce: exportarlos en CSV y convertirlos con `npm run convertir` de la plantilla C.", "", "## Revisar a mano", ""]
    for ptype, s, new, notes in report:
        if notes:
            L.append(f"- `{'blog' if ptype == 'post' else 'paginas'}/{s}.md` ({new}): " + "; ".join(sorted(set(notes))))
    if not any(n for *_, n in report):
        L.append("- nada especial")
    L += ["", "Antes de publicar: `python build.py && python tools/check.py --release` (falla si queda algún [CONFIRMAR]) y "
          "`python -m seo.auditar http://127.0.0.1:8000 --como https://www.cliente.es` desde plantilla-mantenimiento.", ""]
    (out / "informe.md").write_text("\n".join(L), encoding="utf-8")
    return {"entradas": stats.get("entradas", 0), "paginas": stats.get("páginas", 0), "omitidas": len(skipped), "imagenes": len(seen_img),
            "redirecciones": len(redirs), "solo_htaccess": len(only_ht)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("xml")
    ap.add_argument("--lang", default="es", help="idioma del contenido (uno de site.json > languages)")
    ap.add_argument("--salida", default=str(ROOT / "migracion"))
    ap.add_argument("--sobrescribir", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = run(Path(a.xml), Path(a.salida), a.lang, a.sobrescribir)
    except (ValueError, ET.ParseError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"OK: {r['entradas']} entradas, {r['paginas']} páginas ({r['omitidas']} no publicadas, fuera), {r['imagenes']} imágenes, "
          f"{r['redirecciones']} redirecciones. Ver {a.salida}/informe.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
