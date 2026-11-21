"""Comprobaciones de accesibilidad sin navegador (las usa tools/check.py en cada publicación).

Cubren lo que se puede romper al editar contenido (Markdown con HTML, el CMS, un iframe pegado) y que un generador no evita:
idioma, nombres accesibles de campos, enlaces y botones, títulos de iframes, zoom, orden de tabulación, vídeo que suena solo o sin subtítulos,
textos alternativos que son nombres de archivo, saltos en los encabezados e ids duplicados. Criterios WCAG 2.2 entre corchetes.
La prueba con navegador (tools/axe.py) y la revisión manual de la skill accesibilidad-cliente siguen haciendo falta.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
NO_NAME_INPUTS = {"hidden", "submit", "button", "reset", "image"}
GENERIC_LINKS = {"aquí", "aqui", "pincha aquí", "pulsa aquí", "haz clic aquí", "click aquí", "clic aquí", "más", "mas", "ver más", "leer más",
                 "más información", "here", "click here", "more", "read more", "learn more", "link", "enlace"}
FILENAME_ALT = re.compile(r"(\.(jpe?g|png|webp|gif|svg|avif)$)|^(img|dsc|image|imagen|foto|photo|pxl)[_-]?\d+|^(imagen|foto|image|photo|picture)$", re.I)


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "line")

    def __init__(self, tag, attrs, parent, line=0):
        self.tag, self.attrs, self.children, self.parent, self.line = tag, attrs, [], parent, line

    def text(self, skip_hidden=True) -> str:
        out = []
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            elif not (skip_hidden and (c.attrs.get("aria-hidden") == "true" or c.tag in ("script", "style"))):
                out.append(c.attrs.get("alt", "") if c.tag == "img" else c.text(skip_hidden))
        return " ".join("".join(out).split())

    def ancestors(self):
        n = self.parent
        while n is not None:
            yield n
            n = n.parent

    def walk(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.walk()


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur, self.getpos()[0])
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur, self.getpos()[0]))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse(html: str) -> Node:
    b = _Builder()
    b.feed(html)
    return b.root


def _hidden(n: Node) -> bool:
    return any(a.attrs.get("aria-hidden") == "true" or "hidden" in a.attrs for a in [n, *n.ancestors()])


def check(html: str, langs: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Devuelve (errores, avisos) de una página. langs: idiomas válidos de la web (None = cualquiera, p. ej. en una web ajena)."""
    root = parse(html)
    errs, warns = [], []
    nodes = list(root.walk())
    by_id: dict[str, int] = {}
    for n in nodes:
        if "id" in n.attrs:
            by_id[n.attrs["id"]] = by_id.get(n.attrs["id"], 0) + 1
    labels_for = {n.attrs.get("for") for n in nodes if n.tag == "label" and n.attrs.get("for")}

    def labelled(n: Node) -> bool:
        a = n.attrs
        if a.get("aria-label", "").strip() or a.get("title", "").strip():
            return True
        if a.get("aria-labelledby") and all(i in by_id for i in a["aria-labelledby"].split()):
            return True
        if a.get("id") and a["id"] in labels_for:
            return True
        return any(x.tag == "label" for x in n.ancestors())

    html_el = next((n for n in nodes if n.tag == "html"), None)
    lang = (html_el.attrs.get("lang", "") if html_el else "").strip()
    if not lang:
        errs.append("<html> sin atributo lang: el lector de pantalla no sabe en qué idioma leer [3.1.1]")
    elif langs and lang.split("-")[0] not in langs:
        errs.append(f"<html lang=\"{lang}\"> no es uno de los idiomas de la web ({', '.join(langs)}) [3.1.1]")

    for dup, k in by_id.items():
        if k > 1:
            errs.append(f"id duplicado «{dup}» ({k} veces): rompe etiquetas y referencias [4.1.2]")

    level = 0
    for n in nodes:
        t, a = n.tag, n.attrs
        if t == "meta" and a.get("name", "").lower() == "viewport":
            c = a.get("content", "").replace(" ", "").lower()
            m = re.search(r"maximum-scale=([\d.]+)", c)
            if "user-scalable=no" in c or "user-scalable=0" in c or (m and float(m.group(1)) < 2):
                errs.append("el viewport impide ampliar la página (user-scalable=no o maximum-scale bajo) [1.4.4]")
        if a.get("tabindex", "").strip().lstrip("+").isdigit() and int(a["tabindex"]) > 0:
            errs.append(f"<{t} tabindex=\"{a['tabindex']}\">: un tabindex positivo desordena el recorrido con el teclado [2.4.3]")
        if t in ("video", "audio") and "autoplay" in a and "muted" not in a:
            errs.append(f"<{t} autoplay> con sonido: no puede sonar nada solo al abrir la página [1.4.2]")
        if t in ("video", "audio") and "autoplay" in a and "controls" not in a:
            errs.append(f"<{t} autoplay> sin controls: tiene que poder pararse [2.2.2]")
        if t == "video" and "data-sin-voz" not in a and not any(
                isinstance(c, Node) and c.tag == "track" and c.attrs.get("kind", "subtitles") in ("captions", "subtitles") and c.attrs.get("src")
                for c in n.walk()):
            errs.append(f"<video> sin subtítulos (<track kind=\"captions\">): si no tiene voz, data-sin-voz [1.2.2]")
        if t == "iframe" and not a.get("title", "").strip() and not a.get("aria-label", "").strip():
            errs.append(f"<iframe src=\"{a.get('src', '')[:60]}\"> sin title [4.1.2]")
        if t == "img" and "alt" in a and FILENAME_ALT.search(a["alt"].strip()):
            errs.append(f"<img alt=\"{a['alt']}\">: el texto alternativo es un nombre de archivo o genérico; describe la imagen [1.1.1]")
        if t == "img" and a.get("alt", None) == "" and not _hidden(n) and not any(x.tag in ("a", "button") for x in n.ancestors()) \
                and a.get("role") not in ("presentation", "none") and any(x.tag == "main" for x in n.ancestors()):
            warns.append(f"<img src=\"{a.get('src', '')[:60]}\" alt=\"\">: ¿es decorativa? Si aporta información, descríbela [1.1.1]")
        if t in ("input", "select", "textarea") and a.get("type", "text").lower() not in NO_NAME_INPUTS and not labelled(n):
            errs.append(f"<{t} name=\"{a.get('name', '')}\"> sin etiqueta: cada campo necesita <label> [1.3.1, 4.1.2]")
        if t == "a" and "href" in a and not (a.get("aria-hidden") == "true" and a.get("tabindex") == "-1"):
            name = a.get("aria-label", "").strip() or n.text()
            if not name and not (a.get("aria-labelledby") and all(i in by_id for i in a["aria-labelledby"].split())):
                errs.append(f"enlace sin texto (href=\"{a['href'][:60]}\"): una imagen dentro necesita alt o el enlace aria-label [2.4.4, 4.1.2]")
            elif name.lower().strip(" .:→»") in GENERIC_LINKS:
                warns.append(f"enlace «{name}» (href=\"{a['href'][:60]}\"): fuera de contexto no dice adónde lleva [2.4.4]")
        if t == "button" and not (a.get("aria-label", "").strip() or n.text() or a.get("title", "").strip()):
            errs.append("<button> sin texto ni aria-label [4.1.2]")
        if re.fullmatch(r"h[1-6]", t) and not _hidden(n):
            lv = int(t[1])
            if not n.text():
                errs.append(f"<{t}> vacío [2.4.6]")
            if level and lv > level + 1:
                errs.append(f"salto de encabezado de <h{level}> a <{t}> («{n.text()[:40]}»): usa los niveles en orden [1.3.1]")
            level = lv
        if t == "table" and not any(x.tag == "th" for x in n.walk()):
            warns.append("tabla sin encabezados (<th>): si es de datos, la primera fila o columna debe serlo [1.3.1]")
        if t == "a" and re.search(r"\.pdf($|[?#])", a.get("href", ""), re.I):
            warns.append(f"enlace a PDF ({a['href'][:60]}): comprobar que el PDF es accesible o dar el contenido en HTML")
    return errs, warns
