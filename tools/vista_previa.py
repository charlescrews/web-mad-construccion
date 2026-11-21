"""Junta public/ en un solo HTML para enseñar la web como página privada. La web real es public/.

Cada página (en todos los idiomas) es una vista con su cabecera, su contenido, su pie y su barra móvil, y se abre con #nombre
(#inicio, #servicios, #en-services…). Los enlaces internos, las imágenes, la fuente y los scripts propios van dentro del archivo.
Solo en la vista previa: lo que falta confirmar se ve como una nota «Pendiente» resaltada.

    python tools/vista_previa.py public vista-previa/index.html
    python tools/vista_previa.py public vista-previa/index.html --sin-pendientes   # para el cliente: sin notas «Pendiente» ni franja de aviso

Los [CONFIRMAR] siguen en la web real y check.py --release no la publica mientras quede alguno.
"""
import base64
import re
import sys
from pathlib import Path

pub, out = Path(sys.argv[1]), Path(sys.argv[2])
SIN_PENDIENTES = "--sin-pendientes" in sys.argv[3:]
MIME = {".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2"}
PROPIOS = ("presupuesto.js", "idioma.js")  # scripts propios que se meten en línea si alguna página los usa

# Páginas: cada index.html de public/ (la portada de cada idioma incluida), menos las de servicio sin contenido para el cliente.
OMITIR = {"pedido", "order", "gracias", "thanks", "offline"}
paginas = {}
for f in sorted(pub.rglob("index.html")):
    rel = f.parent.relative_to(pub).as_posix()
    rel = "" if rel == "." else rel
    if rel and rel.split("/")[-1] in OMITIR:
        continue
    vid = rel.replace("/", "-") or "inicio"
    paginas["/" + rel + ("/" if rel else "")] = (vid, f)


def data_uri(rel):
    p = pub / rel.lstrip("/")
    return f"data:{MIME[p.suffix]};base64," + base64.b64encode(p.read_bytes()).decode()


def variante_ligera(rel):
    """La foto de 800 px si existe (foto-800.webp): la vista previa pesa mucho menos y en pantalla se ve igual."""
    p = pub / rel.lstrip("/")
    v = p.with_name(f"{p.stem}-800{p.suffix}")
    return "/" + v.relative_to(pub).as_posix() if p.suffix == ".webp" and v.exists() else rel


def enlaces(h):
    h = re.sub(r'href="(/[^"#?]*)"', lambda m: f'href="#{paginas[m.group(1)][0]}"' if m.group(1) in paginas else m.group(0), h)
    h = re.sub(r'\s(srcset|sizes)="[^"]*"', "", h)
    # La ruta original se guarda en data-src: los estilos que dependen de ella (img[src*="/iconos/"]) siguen valiendo.
    h = re.sub(r'src="(/[^"]+\.(?:svg|webp|png|jpg))"', lambda m: f'data-src="{m.group(1)}" src="{data_uri(variante_ligera(m.group(1)))}"', h)
    nota = "" if SIN_PENDIENTES else r'<mark class="pendiente">Pendiente: \1</mark>'
    h = re.sub(r">([^<]+)", lambda t: ">" + re.sub(r"\s*\[CONFIRMAR:\s*([^\]]*)\]" if SIN_PENDIENTES else r"\[CONFIRMAR:\s*([^\]]*)\]", nota, t.group(1)), h)
    return h


idx = (pub / "index.html").read_text()
css = "".join(re.findall(r"<style>(.*?)</style>", idx, re.S))
css = re.sub(r"url\('(/fonts/[^']+)'\)", lambda m: f"url('{data_uri(m.group(1))}')", css) + (pub / "style.css").read_text()
css = css.replace('[src*="', '[data-src*="').replace('[src^="', '[data-src^="').replace('[src$="', '[data-src$="')

vistas, usados = [], set()
for ruta, (vid, f) in paginas.items():
    s = f.read_text()
    lang = re.search(r'<html lang="([^"]+)"', s).group(1)
    titulo = re.search(r"<title>(.*?)</title>", s).group(1)
    cuerpo = s[s.index(">", s.index("<body")) + 1:s.rindex("</body>")]
    for js in PROPIOS:
        if f'src="/{js}"' in cuerpo:
            usados.add(js)
    cuerpo = re.sub(r"<script\b[^>]*>.*?</script>", "", cuerpo, flags=re.S)
    sin_barra = "" if 'class="barra-movil"' in cuerpo else " data-sin-barra"
    vistas.append(f'<div class="vista" id="v-{vid}" lang="{lang}" data-titulo="{titulo}"{sin_barra} hidden>{enlaces(cuerpo)}</div>')

def propio(js):
    s = (pub / js).read_text()
    if js == "idioma.js":
        # En la web cada página carga el script; aquí todas las vistas están en un archivo: se vuelve a evaluar en cada vista.
        s = s.replace('document.querySelectorAll(".aviso-idioma[data-idioma]")', 'document.querySelectorAll(".vista:not([hidden]) .aviso-idioma[data-idioma]")')
        s = "window.__idiomaPrevia = function () {\n" + s + "\n};"
    return f"<script>{s}</script>"


propios = "".join(propio(js) for js in PROPIOS if js in usados)
html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Vista previa</title>
<link rel="icon" href="{data_uri('/favicon.svg')}" type="image/svg+xml">
<style>{css}
mark.pendiente{{background:#F3E9D2;color:#3D3424;border:1px dashed #A99B8B;border-radius:4px;padding:0 .3em;font-size:.92em}}
.aviso-previa{{background:#A99B8B;color:#1F2328;font:600 .9rem/1.4 system-ui,sans-serif;text-align:center;padding:.5rem 1rem;margin:0}}
@media (max-width: 47.99rem) and (pointer: coarse) {{ .vista:has(> .barra-movil) {{ padding-bottom: 4.5rem; }} }}
</style>
</head>
<body>
{"" if SIN_PENDIENTES else '<p class="aviso-previa">Vista previa para revisar. Lo marcado «Pendiente» espera tus respuestas.</p>'}
{''.join(vistas)}
{propios}
<script>
(function () {{
  var vistas = document.querySelectorAll('.vista');
  var primera = true;
  function mostrar() {{
    var id = (location.hash || '#inicio').slice(1);
    // Al abrir la vista previa se empieza siempre por el inicio, aunque la dirección recuerde la última sección visitada.
    if (primera) {{
      primera = false;
      if (id !== 'inicio') {{ try {{ location.replace('#inicio'); }} catch (e) {{ /* sin cambiar la dirección */ }} id = 'inicio'; }}
    }}
    var v = document.getElementById('v-' + id);
    if (!v) {{
      var actual = document.querySelector('.vista:not([hidden])');
      var destino = actual && actual.querySelector('#' + CSS.escape(id));
      if (destino) {{ if (!destino.hasAttribute('tabindex')) destino.setAttribute('tabindex', '-1'); destino.focus(); }}
      return;
    }}
    vistas.forEach(function (x) {{ x.hidden = x !== v; }});
    document.documentElement.lang = v.getAttribute('lang');
    document.title = v.getAttribute('data-titulo') + ' · vista previa';
    v.querySelectorAll('details[open]').forEach(function (d) {{ d.open = false; }});
    window.scrollTo({{ top: 0, behavior: 'instant' }});
    if (window.__idiomaPrevia) window.__idiomaPrevia();
  }}
  window.addEventListener('hashchange', mostrar);
  mostrar();
}})();
</script>
</body>
</html>
"""
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html)
print(f"{len(html) // 1024} KB · {len(vistas)} vistas")
