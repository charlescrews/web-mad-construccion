#!/usr/bin/env python3
"""Comprobaciones de calidad de public/ antes de publicar.

    python tools/check.py            # avisos + errores bloqueantes (enlaces rotos, HTML básico)
    python tools/check.py --release  # además, textos de relleno y datos legales => error

Devuelve código 1 si hay errores (sirve para GitHub Actions).
"""
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public"
RELEASE = "--release" in sys.argv
CFG = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))

errors, warnings = [], []
# Distingue mayúsculas: "TODO" es relleno, "todo" es una palabra normal.
FILLER = ["[CONFIRMAR", "[pendiente]", "[pending]", "Lorem ipsum", "lorem ipsum", "TODO", "EJEMPLO", "B00000000", "600 000 000",
          "ejemplo-cliente", "Foto del cliente"]
filler_hits: dict[str, list[str]] = {}


# Etiquetas y atributos que el navegador descarga solo, sin que nadie pulse nada: si apuntan a otro dominio, el visitante le manda
# su IP (y a veces cookies) antes de poder consentir. Google Fonts desde su CDN es el caso típico (LG München, 20/1/2022).
RESOURCE_ATTRS = {"script": ("src",), "img": ("src", "srcset"), "source": ("src", "srcset"), "iframe": ("src",), "video": ("src", "poster"),
                  "audio": ("src",), "embed": ("src",), "object": ("data",), "track": ("src",)}
LINK_RELS = {"stylesheet", "preload", "modulepreload", "icon", "apple-touch-icon", "manifest", "preconnect", "dns-prefetch", "prefetch"}


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids, self.imgs_no_alt, self.h1 = [], set(), 0, 0
        self.title = False
        self.resources: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])  # los duplicados los marca tools/a11y.py como error
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("link", "script", "img", "source") and (a.get("href") or a.get("src")):
            self.links.append(a.get("href") or a.get("src"))
        for attr in RESOURCE_ATTRS.get(tag, ()):
            for part in (a.get(attr) or "").split(","):
                if part.strip():
                    self.resources.append((tag, part.strip().split(" ")[0]))
        if tag == "link" and a.get("href") and set((a.get("rel") or "").lower().split()) & LINK_RELS:
            self.resources.append((f"link rel={a.get('rel')}", a["href"]))
        if tag == "img" and "alt" not in a:
            self.imgs_no_alt += 1
        if tag == "h1":
            self.h1 += 1
        if tag == "title":
            self.title = True


if not OUT.exists():
    sys.exit("No existe public/. Ejecuta antes: python build.py")

import importlib.util  # noqa: E402

_a11y_spec = importlib.util.spec_from_file_location("a11y", Path(__file__).with_name("a11y.py"))
a11y = importlib.util.module_from_spec(_a11y_spec)
_a11y_spec.loader.exec_module(a11y)
LANGS = CFG.get("languages", ["es"])

files = list(OUT.rglob("*.html"))
parsed = {}
for f in files:
    txt = f.read_text(encoding="utf-8")
    p = P()
    p.feed(txt)
    parsed[f] = p
    rel = f.relative_to(OUT)
    if p.h1 != 1:
        errors.append(f"{rel}: tiene {p.h1} <h1> (debe tener 1)")
    if not p.title:
        errors.append(f"{rel}: sin <title>")
    if p.imgs_no_alt:
        errors.append(f"{rel}: {p.imgs_no_alt} imagen(es) sin atributo alt")
    # Accesibilidad (tools/a11y.py): lo que se rompe al editar contenido. La prueba en navegador es tools/axe.py.
    a_err, a_warn = a11y.check(txt, LANGS)
    errors.extend(f"{rel}: {e}" for e in a_err)
    warnings.extend(f"{rel}: {w}" for w in a_warn)
    if 'src="http://' in txt or 'href="http://' in txt.replace('href="http://www.w3.org', ''):
        warnings.append(f"{rel}: recursos o enlaces http:// sin cifrar")
    # Etiquetas de medición cargadas sin pasar por el consentimiento (static/consent.js): prohibido.
    for tracker in ("googletagmanager.com", "google-analytics.com", "connect.facebook.net", "gtag(", "fbq("):
        if re.search(r"<script[^>]*>[^<]*" + re.escape(tracker) + r"|<script[^>]+src=\"[^\"]*" + re.escape(tracker), txt):
            errors.append(f"{rel}: etiqueta de medición sin consentimiento ({tracker}); usar site.json > medicion")
    visible = re.sub(r"<script.*?</script>|<[^>]+>", " ", txt, flags=re.S)
    # El texto alternativo también se lee (lectores de pantalla, buscadores): «Foto del cliente pendiente…» no se publica.
    visible += " " + " ".join(html.unescape(a) for a in re.findall(r'<img\b[^>]*\balt="([^"]*)"', txt))
    for word in FILLER:
        if word in visible:
            filler_hits.setdefault(word, []).append(str(rel))
    # Imágenes provisionales (nombre con «provisional»): se cambian por las del cliente antes de entregar.
    if re.search(r'<img\b[^>]*\bsrc="[^"]*provisional[^"/]*"', txt, flags=re.I):
        filler_hits.setdefault("imagen provisional", []).append(str(rel))

# Enlaces internos con UTM o identificadores de clic: al pulsarlos, la visita «cambia» de origen y se pierde la campaña que la trajo
# (static/consent.js guarda el último origen etiquetado). Los UTM son solo para enlaces desde fuera (anuncios, redes, emails, QR).
_SITE_HOST = re.sub(r"^www\.", "", re.sub(r"^https?://([^/:]+).*$", r"\1", CFG["site_url"].lower()))
_TRACK = re.compile(r"[?&](utm_[a-z]+|gclid|gbraid|wbraid|fbclid|msclkid|ttclid)=", re.I)
for f, p in parsed.items():
    for link in p.links:
        m = re.match(r"^(?:https?:)?//([^/:?#]+)", link, re.I)
        internal = not m and not link.startswith(("mailto:", "tel:", "data:", "#")) or (m and re.sub(r"^www\.", "", m.group(1).lower()) == _SITE_HOST)
        if internal and _TRACK.search(link):
            errors.append(f"{f.relative_to(OUT)}: enlace interno con UTM o identificador de clic ({link}): pisa el origen real de la visita; "
                          "los UTM solo en enlaces que vienen de fuera")

for f, p in parsed.items():
    rel = f.relative_to(OUT)
    for link in p.links:
        if link.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
            continue
        path, _, frag = link.partition("#")
        path = path.split("?")[0]
        target = f if not path else OUT / path.lstrip("/")
        if path.endswith("/"):
            target = target / "index.html"
        if not target.exists():
            errors.append(f"{rel}: enlace roto {link}")
        elif frag and target.suffix == ".html" and frag not in parsed[target].ids:
            errors.append(f"{rel}: ancla inexistente {link}")

# --- Recursos de terceros (RGPD y LSSI 22.2): nada se descarga de otro dominio sin consentimiento ---
from urllib.parse import urlparse  # noqa: E402

PRIV = CFG.get("privacidad", {}) or {}
ENC = [e for e in (PRIV.get("encargados") or []) if isinstance(e, dict)]


def _host(u: str) -> str:
    return (urlparse(u).hostname or "").lower() if u.startswith(("http://", "https://", "//")) else ""


ALLOWED = {_host(CFG["site_url"])}
for _u in ((CFG.get("contact_form") or {}).get("endpoint", ""), (CFG.get("catalog") or {}).get("api", ""), (CFG.get("chatbot") or {}).get("script", ""),
           (CFG.get("crm") or {}).get("boletin", ""), CFG.get("cuenta_url", "")):
    if _u:
        ALLOWED.add(_host(_u))
for _e in ENC:  # dominios declarados de un encargado (p. ej. el CDN de imágenes), que ya sale en la política de privacidad
    ALLOWED.update(d.lower() for d in (_e.get("dominios") or []))
ALLOWED.discard("")
GOOGLE_FONTS = ("fonts.googleapis.com", "fonts.gstatic.com")
for f, p in parsed.items():
    rel = f.relative_to(OUT)
    for tag, url in p.resources:
        h = _host(url)
        if not h:
            continue
        if h in GOOGLE_FONTS:
            errors.append(f"{rel}: Google Fonts desde su CDN ({url}): la IP del visitante va a Google sin consentimiento. "
                          "Descargar las fuentes en woff2 a static/fonts/ (site.json > brand.font_files)")
        elif h not in ALLOWED:
            errors.append(f"{rel}: recurso de terceros sin consentimiento <{tag}> {url}. Servirlo desde la web, cambiarlo por un enlace "
                          "(vídeos y mapas: imagen propia que enlaza a YouTube o a Google Maps) o declarar el proveedor en site.json > privacidad.encargados[].dominios")
for css in OUT.rglob("*.css"):
    for m in re.finditer(r"@import\s+(?:url\()?['\"]?([^'\")\s;]+)|url\(\s*['\"]?([^'\")]+)", css.read_text(encoding="utf-8")):
        url = (m.group(1) or m.group(2) or "").strip()
        h = _host(url)
        if h and (h in GOOGLE_FONTS or h not in ALLOWED):
            errors.append(f"{css.relative_to(OUT)}: recurso de terceros en la hoja de estilos ({url}); servirlo desde la web")

# --- Pedido preparado por el asistente (skill asistente-conectado-cliente) ---
_cat = CFG.get("catalog") or {}
_bot = CFG.get("chatbot") or {}
if (_bot.get("script") and _bot.get("bot") or (CFG.get("asistente_voz") or {}).get("activo")) and not _bot.get("proveedores_ia"):
    warnings.append("site.json: chatbot.proveedores_ia vacío: conviene nombrar el proveedor de IA (y el de respaldo, si lo hay) en la privacidad")
if _cat.get("asistente") and not ((CFG.get("chatbot") or {}).get("script") and (CFG.get("chatbot") or {}).get("bot")):
    warnings.append("site.json: catalog.asistente sin chatbot: la página /pedido/ solo la usa el asistente (plantilla-bot con tienda.pagina_pedido)")

# --- Cierres (festivos y vacaciones; el asistente los toma de /asistente.json) ---
import datetime as _dt  # noqa: E402
import os as _os  # noqa: E402
_hoy = _dt.date.fromisoformat(_os.environ["LTR_HOY"]) if _os.environ.get("LTR_HOY") else _dt.date.today()
for _c in (CFG.get("company") or {}).get("cierres") or []:
    try:
        _h = _dt.date.fromisoformat(str(_c.get("hasta") or _c.get("desde")))
    except ValueError:
        continue  # build.py ya para con fechas mal escritas
    if _h < _hoy:
        warnings.append(f"site.json: company.cierres: el cierre que acabó el {_h.isoformat()} ya pasó: quitarlo y añadir los próximos festivos y vacaciones")

# --- Política de privacidad completa antes de entregar ---
_need = set()
if (CFG.get("contact_form") or {}).get("endpoint") or (CFG.get("crm") or {}).get("boletin") or ((CFG.get("catalog") or {}).get("comprar") and (CFG.get("catalog") or {}).get("api")):
    _need.update({"alojamiento", "email"})
if (CFG.get("catalog") or {}).get("comprar") and (CFG.get("catalog") or {}).get("api"):
    _need.add("pagos")
if (CFG.get("whatsapp") or {}).get("avisos"):
    _need.add("whatsapp")  # Meta envía los avisos por cuenta del cliente
if (CFG.get("asistente_voz") or {}).get("activo"):
    _need.add("telefonia")  # Twilio atiende, transcribe y pone la voz por cuenta del cliente (skill agente-voz-cliente)
_app = CFG.get("app") or {}
if any((_app.get("tiendas") or {}).values()):
    _need.add("notificaciones")  # los avisos de la app los entrega Firebase Cloud Messaging por cuenta del cliente
_have = {e.get("servicio") for e in ENC}
if not ENC:
    (errors if RELEASE else warnings).append("site.json: falta privacidad.encargados (quién trata datos por cuenta del cliente; los mismos que config/rgpd.json)")
for _s in sorted(_need - _have) if ENC else []:
    (errors if RELEASE else warnings).append(f"site.json: privacidad.encargados sin el servicio «{_s}» (la política de privacidad debe decir quién lo presta)")

# --- Web instalable y apps (skill apps-moviles-cliente) ---
_manifest = OUT / "manifest.webmanifest"
if _manifest.exists():
    try:
        mf = json.loads(_manifest.read_text(encoding="utf-8"))
    except ValueError:
        mf = None
        errors.append("manifest.webmanifest: JSON no válido")
    if mf is not None:
        site_origin = CFG["site_url"].rstrip("/")
        for k in ("start_url", "scope", "id"):
            v = str(mf.get(k) or "")
            if not (v.startswith("/") and not v.startswith("//")) and not v.startswith(site_origin + "/"):
                errors.append(f"manifest.webmanifest: {k} fuera de la web ({v or 'vacío'})")
        for k in ("name", "short_name", "display", "theme_color", "background_color"):
            if not mf.get(k):
                errors.append(f"manifest.webmanifest: falta {k}")
        ics = mf.get("icons") or []
        if not any(i.get("purpose") == "maskable" for i in ics):
            errors.append("manifest.webmanifest: falta el icono maskable (python tools/iconos.py)")
        for size in ("192x192", "512x512"):
            if not any(i.get("sizes") == size and i.get("purpose", "any") == "any" for i in ics):
                errors.append(f"manifest.webmanifest: falta el icono de {size}")
        for i in ics:
            if not (OUT / str(i.get("src", "")).lstrip("/")).is_file():
                errors.append(f"manifest.webmanifest: no existe el icono {i.get('src')}")
    for f, p in parsed.items():
        txt = f.read_text(encoding="utf-8")
        if 'http-equiv="refresh"' not in txt[:1500] and 'rel="manifest"' not in txt:
            errors.append(f"{f.relative_to(OUT)}: sin <link rel=\"manifest\"> (web instalable)")
    _sw = OUT / "sw.js"
    if not _sw.exists():
        errors.append("sw.js: falta el service worker de la web instalable")
    else:
        _m = re.search(r"const PRECACHE = (\[.*?\]);", _sw.read_text(encoding="utf-8"))
        for u in json.loads(_m.group(1)) if _m else []:
            path = u.split("?")[0]
            t = OUT / path.lstrip("/")
            if not ((t / "index.html").exists() if path.endswith("/") else t.exists()):
                errors.append(f"sw.js: precarga algo que no existe ({u}); el service worker no se instalaría")
for _wk in sorted((OUT / ".well-known").glob("*")) if (OUT / ".well-known").exists() else []:
    if _wk.name.startswith("."):
        continue
    try:
        json.loads(_wk.read_text(encoding="utf-8"))
    except ValueError:
        errors.append(f".well-known/{_wk.name}: JSON no válido (los enlaces con la app dejarían de funcionar)")

for word, where in filler_hits.items():
    (errors if RELEASE else warnings).append(
        f"texto de relleno «{word}» en {len(where)} página(s), p. ej. {where[0]}")

# El dominio de ejemplo de la plantilla sale en canonical, sitemap y Open Graph aunque no se vea en la página.
if any(w in CFG["site_url"] for w in FILLER) or "ejemplo" in CFG["site_url"].lower():
    (errors if RELEASE else warnings).append(f"site.json: site_url es de ejemplo ({CFG['site_url']}): poner el dominio del cliente")

co = CFG.get("company", {})
for field in ("legal_name", "cif", "address", "email"):
    if not co.get(field):
        (errors if RELEASE else warnings).append(f"site.json: falta company.{field} (obligatorio en aviso legal)")
med = CFG.get("medicion", {}) or {}
if any(med.get(k) for k in ("ga4", "google_ads", "meta_pixel")) and not med.get("politica_actualizada"):
    (errors if RELEASE else warnings).append("site.json: medicion.politica_actualizada vacía (fecha de la política de cookies revisada con el cliente)")
crm = CFG.get("crm", {}) or {}
bases = ((crm.get("programa") or {}).get("bases_url") or "").strip()
if bases:
    from urllib.parse import urlparse
    site_host = urlparse(CFG["site_url"]).netloc
    u = urlparse(bases)
    if u.netloc == site_host:
        target = OUT / u.path.lstrip("/")
        if not (target / "index.html").exists() and not target.exists():
            errors.append(f"site.json: crm.programa.bases_url apunta a {u.path}, que no existe en la web (crear la página con las bases del programa)")
    elif RELEASE:
        warnings.append("site.json: las bases del programa de puntos están fuera de la web; comprobar que el enlace funciona")
# --- Declaración de accesibilidad (site.json > accesibilidad) ---
acc = CFG.get("accesibilidad", {}) or {}
acc_state = acc.get("estado") or "parcial"
acc_issues = [x for x in (acc.get("problemas") or []) if isinstance(x, dict) and x.get("que")]
if not (acc.get("fecha_evaluacion") or "").strip():
    (errors if RELEASE else warnings).append("site.json: accesibilidad.fecha_evaluacion vacía (evaluar con tools/axe.py y la revisión manual antes de entregar)")
if acc_state != "total" and not acc_issues:
    (errors if RELEASE else warnings).append(f"site.json: accesibilidad.estado «{acc_state}» sin problemas listados: o se listan, o el estado es «total»")
_cat = CFG.get("catalog") or {}
if _cat.get("comprar") and _cat.get("api") and not (acc.get("descripcion_servicio") or "").strip():
    (errors if RELEASE else warnings).append("site.json: accesibilidad.descripcion_servicio vacía: una tienda online explica cómo funciona el servicio (Ley 11/2023, anexo V)")

# --- Marca (tools/marca.py, skill identidad-marca-cliente): logo y favicon en SVG limpio y vectorial, fuentes autoalojadas con su
# licencia y con todos los caracteres de la web, og.png de 1200×630 ---
_mspec = importlib.util.spec_from_file_location("marca", Path(__file__).with_name("marca.py"))
_marca = importlib.util.module_from_spec(_mspec)
_mspec.loader.exec_module(_marca)
_merr, _mwarn = _marca.revisar(ROOT, OUT)
errors.extend(_merr)
warnings.extend(_mwarn)
if not (OUT / "og.png").exists():
    (errors if RELEASE else warnings).append("Falta static/og.png (imagen al compartir en WhatsApp y redes, 1200×630): python tools/marca.py og")

# Contraste de los colores de marca (tools/brand.py)
import importlib.util
_spec = importlib.util.spec_from_file_location("brand", Path(__file__).with_name("brand.py"))
_brand = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_brand)
_b = dict(CFG["brand"])
_b.setdefault("link", _b["primary"])
_b.setdefault("focus", _b["primary"])
for pairs, minimum in ((_brand.PAIRS, _brand.MIN), (_brand.NONTEXT, _brand.MIN_NONTEXT)):
    for fg, bg, use in pairs:
        r = _brand.contrast(_b[fg], _b[bg])
        if r < minimum:
            errors.append(f"contraste insuficiente {r:.2f}:1 (mínimo {minimum}:1) en {use} ({fg} sobre {bg}); ejecuta python tools/brand.py --fix")

# Peso de imágenes
for img in OUT.rglob("*"):
    if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and img.stat().st_size > 400_000 and img.name != "og.png":
        warnings.append(f"imagen pesada ({img.stat().st_size // 1024} KB): {img.relative_to(OUT)}; usa python tools/images.py")

for w in warnings:
    print("AVISO:", w)
for e in errors:
    print("ERROR:", e)
print(f"{len(files)} páginas revisadas · {len(errors)} errores · {len(warnings)} avisos"
      + (" · modo entrega" if RELEASE else ""))
sys.exit(1 if errors else 0)
