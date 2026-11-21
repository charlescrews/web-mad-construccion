"""Identidad de marca (tools/marca.py, skill identidad-marca-cliente).

Protecciones con test: logo y favicon en SVG sin scripts, eventos, HTML incrustado, imágenes PNG/JPG dentro, nada cargado de fuera,
entidades XML ni rutas del equipo de quien lo diseñó; el logo sin texto vivo y con viewBox; el favicon cuadrado. Fuentes autoalojadas
que existen, son woff2 y llevan su licencia publicada al lado (reconocida o revisada a mano); la primera familia de cada pila,
autoalojada o del sistema; nombres sin caracteres raros; y todos los caracteres de la web en la fuente que los pinta. og.png de
1200×630 (sin él, --release falla). El logo de la cabecera con width y height y sin desbordar a 320 px. `fuente` solo copia los
woff2 pedidos y la licencia, y solo con licencias libres; `logotipo` da trazos con kerning y se para si falta una letra; `og` y
`kit` no piden nada a Internet; el kit se para si algo de la marca falla y da logos vectoriales, PNG transparentes, avatar, fuentes
de escritorio con nombres limpios (o ninguna si la licencia reserva el nombre) y un manual accesible.
"""
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.test_build import PRODUCTS, ROOT, Site

_spec = importlib.util.spec_from_file_location("marca", ROOT / "tools" / "marca.py")
marca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(marca)

HAS_FT = marca.hay_fonttools()
try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    HAS_PW = True
except ImportError:
    HAS_PW = False
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
HAS_AXE = (ROOT / "node_modules" / "axe-core" / "axe.min.js").exists()

FONT = ROOT / "tests" / "datos" / "demo" / "static" / "fonts" / "fraunces-latin-wght-normal.woff2"
OK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><path fill="#9A4B1C" d="M0 0h100v40H0z"/></svg>'
FAV = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#9A4B1C"/></svg>'
OFL = "Copyright 2026 Autor\n\nThis Font Software is licensed under the SIL Open Font License, Version 1.1.\n"


def errores(svg: str, tipo: str = "logo", colores=None):
    return marca.svg_problemas(svg, tipo, colores)


class Svg(unittest.TestCase):
    def test_un_svg_limpio_pasa(self):
        self.assertEqual(errores(OK_SVG), ([], []))
        self.assertEqual(errores(FAV, "favicon"), ([], []))

    def test_scripts_eventos_y_html_incrustado(self):
        self.assertIn("contiene <script>", " ".join(errores(OK_SVG.replace("<path", "<script>alert(1)</script><path"))[0]))
        self.assertIn("atributo de evento «onload»", " ".join(errores(OK_SVG.replace("<svg ", '<svg onload="alert(1)" '))[0]))
        self.assertIn("<foreignObject>", " ".join(errores(OK_SVG.replace("<path", "<foreignObject><p>x</p></foreignObject><path"))[0]))

    def test_imagen_incrustada_no_es_vectorial(self):
        e, _ = errores(OK_SVG.replace("<path", '<image href="data:image/png;base64,iVBORw0KGgo=" width="10" height="10"/><path'))
        self.assertIn("imagen incrustada", " ".join(e))

    def test_nada_de_fuera(self):
        e, _ = errores(OK_SVG.replace("<path", '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="https://cdn.x.es/a.svg#a"/><path'))
        self.assertIn("carga algo de fuera", " ".join(e))
        e, _ = errores(OK_SVG.replace("<path", '<a href="javascript:alert(1)"><rect width="1" height="1"/></a><path'))
        self.assertIn("carga algo de fuera", " ".join(e))
        e, _ = errores(OK_SVG.replace("<path", "<style>@import url(https://fonts.googleapis.com/css2?family=X);</style><path"))
        self.assertIn("hoja de estilo que carga algo de fuera", " ".join(e))
        e, _ = errores(OK_SVG.replace("<path ", '<path style="fill:url(https://x.es/p.svg#g)" '))
        self.assertIn("estilo que carga algo de fuera", " ".join(e))

    def test_texto_vivo_en_el_logo_falla_y_en_el_favicon_avisa(self):
        con_texto = OK_SVG.replace("</svg>", '<text x="0" y="30" font-family="Georgia">La Espiga</text></svg>')
        e, _ = errores(con_texto)
        self.assertIn("texto sin convertir a trazos", " ".join(e))
        e, w = errores(FAV.replace("</svg>", '<text x="8" y="22">E</text></svg>'), "favicon")
        self.assertEqual(e, [])
        self.assertIn("texto sin convertir a trazos", " ".join(w))

    def test_sin_viewbox_y_favicon_no_cuadrado(self):
        self.assertIn("sin viewBox", " ".join(errores(OK_SVG.replace(' viewBox="0 0 100 40"', ' width="100" height="40"'))[0]))
        self.assertIn("favicon no cuadrado", " ".join(errores(OK_SVG, "favicon")[0]))

    def test_entidades_rutas_y_restos_del_editor(self):
        e, _ = errores('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY ns_a "http://ns.adobe.com/">]>' + OK_SVG)
        self.assertIn("entidades XML", " ".join(e))
        ink = OK_SVG.replace("<svg ", '<svg xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" inkscape:export-filename="/home/ana/clientes/logo.png" ')
        e, w = errores(ink)
        self.assertIn("ruta del equipo", " ".join(e))
        self.assertIn("restos del programa de diseño", " ".join(w))
        e, _ = errores(OK_SVG.replace("<svg ", '<svg data-origen="C:\\Users\\ana\\logo.ai" '))
        self.assertIn("ruta del equipo", " ".join(e))

    def test_avisos_de_proporcion_peso_y_colores_fuera_de_la_marca(self):
        _, w = errores(OK_SVG.replace("0 0 100 40", "0 0 700 40"))
        self.assertIn("muy alargado", " ".join(w))
        _, w = errores(OK_SVG.replace("</svg>", "<desc>" + "x" * 31000 + "</desc></svg>"))
        self.assertIn("pesa", " ".join(w))
        _, w = errores(OK_SVG.replace("#9A4B1C", "#9A4C1C"), colores={"#9A4B1C", "#2A211B"})
        self.assertIn("#9A4C1C", " ".join(w))
        _, w = errores(OK_SVG.replace('fill="#9A4B1C"', 'style="fill:#9a4b1c"'), colores={"#9A4B1C"})
        self.assertEqual(w, [], "mismo color en minúsculas y en style")
        _, w = errores(OK_SVG.replace('fill="#9A4B1C"', 'style="fill:#123456"'), colores={"#9A4B1C"})
        self.assertIn("#123456", " ".join(w), "también los colores de style")


class Fuentes(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "fonts").mkdir()
        (self.dir / "fonts" / "x-latin.woff2").write_bytes(b"wOF2" + b"\0" * 64)
        (self.dir / "fonts" / "x-LICENSE.txt").write_text(OFL)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def brand(self, **f):
        entry = {"family": "Xilo", "file": "x-latin.woff2", "licencia": "x-LICENSE.txt", **f}
        return {"font_heading": "'Xilo', Georgia, serif", "font_body": "system-ui, sans-serif", "font_files": [entry]}

    def test_fuente_completa_pasa(self):
        self.assertEqual(marca.fuentes_problemas(self.brand(), self.dir), ([], []))

    def test_familia_y_archivo_obligatorios(self):
        b = self.brand()
        del b["font_files"][0]["family"]
        self.assertIn("cada fuente lleva «family» y «file»", " ".join(marca.fuentes_problemas(b, self.dir)[0]))

    def test_archivo_que_no_existe_o_no_es_woff2(self):
        self.assertIn("no existe static/fonts/y.woff2", " ".join(marca.fuentes_problemas(self.brand(file="y.woff2"), self.dir)[0]))
        (self.dir / "fonts" / "x-latin.woff2").write_bytes(b"\x00\x01\x00\x00" + b"\0" * 64)  # un TTF con otra extensión
        self.assertIn("no es un woff2", " ".join(marca.fuentes_problemas(self.brand(), self.dir)[0]))

    def test_licencia_obligatoria_y_publicada_al_lado(self):
        b = self.brand()
        del b["font_files"][0]["licencia"]
        self.assertIn("falta «licencia»", " ".join(marca.fuentes_problemas(b, self.dir)[0]))
        self.assertIn("no existe la licencia", " ".join(marca.fuentes_problemas(self.brand(licencia="otra.txt"), self.dir)[0]))
        (self.dir / "LICENCIA-fuera.txt").write_text(OFL)  # existe, pero fuera de static/fonts/ (no se publicaría con la fuente)
        self.assertIn("no existe la licencia", " ".join(marca.fuentes_problemas(self.brand(licencia="../LICENCIA-fuera.txt"), self.dir)[0]))

    def test_licencia_no_reconocida_exige_revision(self):
        (self.dir / "fonts" / "x-LICENSE.txt").write_text("Licencia de escritorio. Uso web: consultar.")
        self.assertIn("licencia que no es OFL", " ".join(marca.fuentes_problemas(self.brand(), self.dir)[0]))
        self.assertEqual(marca.fuentes_problemas(self.brand(licencia_revisada="2026-10-20"), self.dir)[0], [])

    def test_nombre_reservado_avisa(self):
        (self.dir / "fonts" / "x-LICENSE.txt").write_text('Copyright 2026 Autor, with Reserved Font Name "Xilo".\n\n' + OFL)
        _, w = marca.fuentes_problemas(self.brand(), self.dir)
        self.assertIn("reserva el nombre", " ".join(w))

    def test_primera_familia_sin_autoalojar_falla(self):
        b = self.brand()
        b["font_body"] = "'Inter', sans-serif"
        self.assertIn("«Inter» no está en font_files ni es del sistema", " ".join(marca.fuentes_problemas(b, self.dir)[0]))
        b["font_body"] = "-apple-system, 'Segoe UI', Roboto, sans-serif"
        self.assertEqual(marca.fuentes_problemas(b, self.dir)[0], [])

    def test_nombres_con_caracteres_raros(self):
        e, _ = marca.fuentes_problemas(self.brand(family="X'}body{display:none"), self.dir)
        self.assertIn("caracteres raros", " ".join(e))
        e, _ = marca.fuentes_problemas(self.brand(file="../../x.woff2"), self.dir)
        self.assertIn("caracteres raros", " ".join(e))

    def test_avisos_de_uso(self):
        b = self.brand()
        b["font_heading"] = "Georgia"
        _, w = marca.fuentes_problemas(b, self.dir)
        self.assertIn("sin familia genérica", " ".join(w))
        self.assertIn("declarada pero no se usa", " ".join(w))
        (self.dir / "fonts" / "x-latin.woff2").write_bytes(b"wOF2" + b"\0" * 160_000)
        self.assertIn("pesa 156 KB", " ".join(marca.fuentes_problemas(self.brand(), self.dir)[1]))
        b = self.brand()
        for fam in ("Yuca", "Zeta"):
            b["font_files"].append({"family": fam, "file": "x-latin.woff2", "licencia": "x-LICENSE.txt"})
        b["font_body"] = "Yuca, Zeta, sans-serif"
        self.assertIn("3 familias propias", " ".join(marca.fuentes_problemas(b, self.dir)[1]))


class Revisar(unittest.TestCase):
    """En la web generada: tools/check.py (y --release)."""

    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, **cfg) -> Site:
        s = Site(products=PRODUCTS, **cfg)
        self.sites.append(s)
        return s

    def release(self, s: Site) -> tuple[int, str]:
        r = subprocess.run([sys.executable, "-B", "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_la_plantilla_pasa(self):
        s = self.site()
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertEqual(code, 0, out)
        self.assertNotIn("logo (", out)
        self.assertNotIn("favicon (", out)

    def test_check_falla_con_un_logo_con_texto(self):
        s = self.site()
        (s.dir / "static" / "img" / "logo.svg").write_text(OK_SVG.replace("</svg>", "<text x='0' y='30'>La Espiga</text></svg>"))
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("ERROR: logo (static/img/logo.svg): texto sin convertir a trazos", out)

    def test_check_falla_con_un_favicon_con_script(self):
        s = self.site()
        (s.dir / "static" / "favicon.svg").write_text(FAV.replace("</svg>", "<script>alert(1)</script></svg>"))
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertIn("ERROR: favicon (static/favicon.svg): contiene <script>", out)

    def test_check_falla_con_una_fuente_sin_licencia(self):
        s = self.site()
        (s.dir / "static" / "fonts" / "fraunces-LICENSE.txt").unlink()
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("no existe la licencia static/fonts/fraunces-LICENSE.txt", out)

    @unittest.skipUnless(HAS_FT, "faltan fontTools y brotli")
    def test_caracteres_que_la_fuente_no_tiene(self):
        s = self.site()
        (s.dir / "content" / "es" / "prueba.md").write_text("---\ntitle: Prueba\ndescription: Prueba\n---\n\n## Főzelék de Budapest\n\n## Pan → 🍞\n\nTexto.\n", encoding="utf-8")
        # «otra» va antes en orden alfabético: si el texto normal contara para la fuente de los títulos, el error citaría esta página
        (s.dir / "content" / "es" / "otra.md").write_text("---\ntitle: Otra\ndescription: Otra\n---\n\nUn párrafo con ő.\n", encoding="utf-8")
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("la fuente «Fraunces» no tiene «ő» (U+0151), que sale en prueba/index.html", out)
        self.assertEqual(out.count("U+0151"), 1, "el texto normal va en la fuente del sistema: solo cuenta el título")
        self.assertNotIn("U+2192", out, "flechas y emojis caen a otra fuente sin que se note: no cuentan")
        self.assertNotIn("U+1F35E", out)

    def test_sin_fonttools_avisa(self):
        s = self.site()
        self.assertEqual(s.build()[0], 0)
        antes = marca.hay_fonttools
        marca.hay_fonttools = lambda: False
        try:
            errs, warns = marca.revisar(s.dir, s.dir / "public")
        finally:
            marca.hay_fonttools = antes
        self.assertEqual(errs, [])
        self.assertIn("sin fontTools y brotli no se comprueba", " ".join(warns))

    def test_og_de_medida_justa_y_obligatoria_al_entregar(self):
        s = self.site()
        self.assertEqual(s.build()[0], 0)
        code, out = self.release(s)
        self.assertNotIn("og.png", out)
        png = (s.dir / "static" / "og.png").read_bytes()
        (s.dir / "static" / "og.png").write_bytes(png[:16] + (1200).to_bytes(4, "big") + (600).to_bytes(4, "big") + png[24:])
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertIn("ERROR: static/og.png mide 1200×600", out)
        (s.dir / "static" / "og.png").write_bytes(b"\xff\xd8\xff\xe0" + b"\0" * 40)
        self.assertEqual(s.build()[0], 0)
        self.assertIn("ERROR: static/og.png no es un PNG", s.check()[1])
        (s.dir / "static" / "og.png").unlink()
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertIn("AVISO: Falta static/og.png", out)
        code, out = self.release(s)
        self.assertIn("ERROR: Falta static/og.png", out)

    def test_logo_con_medidas_en_la_cabecera(self):
        s = self.site()
        self.assertEqual(s.build()[0], 0)
        vb = marca.viewbox((s.dir / "static" / "img" / "logo.svg").read_text())
        self.assertIn(f'class="logo" width="{round(vb[2])}" height="{round(vb[3])}"', s.read("index.html"))


def fake_tgz(path: Path, *, license_type="OFL-1.1", con_licencia=True, extra: dict | None = None, ejes=None) -> Path:
    ejes = {"wght": {"min": "200", "max": "800"}} if ejes is None else ejes
    files = {"package/package.json": json.dumps({"name": "@fontsource-variable/xilo", "version": "1.2.3", "license": license_type}).encode(),
             "package/metadata.json": json.dumps({"family": "Xilo", "subsets": ["latin", "latin-ext"], "variable": ejes}).encode(),
             "package/files/xilo-latin-wght-normal.woff2": b"wOF2" + b"\1" * 32,
             "package/files/xilo-latin-ext-wght-normal.woff2": b"wOF2" + b"\2" * 32,
             "package/files/xilo-latin-wght-italic.woff2": b"wOF2" + b"\3" * 32,
             "package/index.css": b"@font-face{src:url(https://fonts.gstatic.com/x.woff2)}"}
    if con_licencia:
        files["package/LICENSE"] = OFL.encode()
    files.update(extra or {})
    with tarfile.open(path, "w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return path


class Fuente(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_copia_solo_lo_pedido_y_la_licencia(self):
        dest = self.dir / "fonts"
        out = marca.fuente("xilo", destino=dest, tgz=fake_tgz(self.dir / "p.tgz", extra={"package/../../fuera.txt": b"x"}))
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["xilo-LICENSE.txt", "xilo-latin-wght-normal.woff2"])
        self.assertFalse((self.dir / "fuera.txt").exists())
        self.assertEqual(out, [{"family": "Xilo", "file": "xilo-latin-wght-normal.woff2", "weight": "200 800", "style": "normal",
                                "licencia": "xilo-LICENSE.txt", "origen": "@fontsource-variable/xilo@1.2.3"}])
        self.assertEqual(marca.fuentes_problemas({"font_heading": "Xilo, serif", "font_files": out}, self.dir)[0], [])

    def test_italica_y_otro_subconjunto(self):
        out = marca.fuente("xilo", destino=self.dir / "f", italica=True, tgz=fake_tgz(self.dir / "p.tgz"))
        self.assertEqual([o["style"] for o in out], ["normal", "italic"])
        out = marca.fuente("xilo", destino=self.dir / "g", subconjunto="latin-ext", tgz=fake_tgz(self.dir / "p.tgz"))
        self.assertEqual(out[0]["file"], "xilo-latin-ext-wght-normal.woff2")

    def test_licencias_no_libres_y_sin_licencia(self):
        with self.assertRaises(SystemExit) as c:
            marca.fuente("xilo", destino=self.dir / "f", tgz=fake_tgz(self.dir / "p.tgz", license_type="SEE LICENSE IN EULA"))
        self.assertIn("solo OFL-1.1", str(c.exception))
        with self.assertRaises(SystemExit) as c:
            marca.fuente("xilo", destino=self.dir / "f", tgz=fake_tgz(self.dir / "q.tgz", con_licencia=False))
        self.assertIn("no trae LICENSE", str(c.exception))
        self.assertFalse((self.dir / "f").exists() and any((self.dir / "f").iterdir()), "no se copia nada")

    def test_id_y_subconjunto_validos(self):
        for bad in ("../x", "Xilo", "x y"):
            with self.assertRaises(SystemExit) as c:
                marca.fuente(bad, destino=self.dir / "f", tgz=fake_tgz(self.dir / "p.tgz"))
            self.assertIn("no es un id de Fontsource", str(c.exception))
        with self.assertRaises(SystemExit) as c:
            marca.fuente("xilo", destino=self.dir / "f", tgz=fake_tgz(self.dir / "s.tgz", ejes={"opsz": {"min": "8", "max": "72"}}))
        self.assertIn("no es variable en peso", str(c.exception))
        with self.assertRaises(SystemExit) as c:
            marca.fuente("xilo", destino=self.dir / "f", subconjunto="cyrillic", tgz=fake_tgz(self.dir / "p.tgz"))
        self.assertIn("no tiene el subconjunto cyrillic", str(c.exception))


@unittest.skipUnless(HAS_FT, "faltan fontTools y brotli")
class Logotipo(unittest.TestCase):
    def test_trazos_con_kerning_y_simbolo(self):
        svg = marca.logotipo("La Espiga", FONT, peso=650, color="#2A211B", simbolo=ROOT / "tests" / "datos" / "demo" / "marca" / "simbolo.svg")
        e, w = marca.svg_problemas(svg, "logo", {"#2A211B", "#9A4B1C", "#FBF7F2"})
        self.assertEqual((e, w), ([], []))
        self.assertNotIn("<text", svg)
        self.assertIn('aria-label="La Espiga"', svg)
        self.assertIn("<circle", svg, "el símbolo va dentro")
        f = marca._abrir_fuente(FONT, 650, {})
        cm = f.getBestCmap()
        self.assertLess(marca._kerning(f, [cm[ord("A")], cm[ord("V")]])[0], 0, "AV se acerca")
        sin = marca.viewbox(marca.logotipo("AVA", FONT, peso=650))[2]
        abierto = marca.viewbox(marca.logotipo("AVA", FONT, peso=650, espaciado=0.1))[2]
        self.assertGreater(abierto, sin)

    def test_letra_que_falta_y_simbolo_con_problemas(self):
        with self.assertRaises(SystemExit) as c:
            marca.logotipo("Főzelék", FONT)
        self.assertIn("no tiene ő", str(c.exception))
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "s.svg").write_text(OK_SVG.replace("<path", "<script>x</script><path"))
            with self.assertRaises(SystemExit) as c:
                marca.logotipo("La Espiga", FONT, simbolo=tmp / "s.svg")
            self.assertIn("símbolo", str(c.exception))
        finally:
            shutil.rmtree(tmp)

    def test_peso_fuera_de_ejes_y_color(self):
        with self.assertRaises(SystemExit):
            marca.logotipo("La", FONT, ejes={"opsz": 72})  # este archivo de Fraunces solo tiene wght
        with self.assertRaises(SystemExit):
            marca.logotipo("La", FONT, color="red")


class Proyecto:
    """Copia de la plantilla para og y kit (escriben en static/ y marca/)."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="marca-"))
        for name in ("site.json", "static", "tools", "marca"):
            src = (ROOT if name == "tools" else ROOT / "tests" / "datos" / "demo") / name
            (shutil.copytree if src.is_dir() else shutil.copy)(src, self.dir / name, **({"ignore": shutil.ignore_patterns("entrega*")} if src.is_dir() else {}))

    def cfg(self, **brand):
        p = self.dir / "site.json"
        c = json.loads(p.read_text(encoding="utf-8"))
        c["brand"].update(brand)
        p.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


@unittest.skipUnless(HAS_PW and HAS_FT and HAS_PIL, "faltan Playwright, fontTools o Pillow")
class OgYKit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nav = marca.Navegador().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.nav.__exit__(None, None, None)

    def setUp(self):
        self.nav.peticiones.clear()
        self.nav.consola.clear()
        self.p = Proyecto()

    def tearDown(self):
        self.p.cleanup()

    def test_og_con_foto_y_sin_ella(self):
        foto = self.p.dir / "foto.webp"
        Image.new("RGB", (1600, 1000), (150, 90, 40)).save(foto, "WEBP")
        out = marca.og(self.p.dir, foto, "Pan de masa madre", nav=self.nav)
        with Image.open(out) as im:
            self.assertEqual(im.size, (1200, 630))
            self.assertEqual(im.convert("RGB").getpixel((10, 10)), (150, 90, 40), "la foto de fondo")
            self.assertEqual(im.convert("RGB").getpixel((80, 560)), (0xFB, 0xF7, 0xF2), "el recuadro claro del logo")
        (self.p.dir / "static" / "og.png").unlink()
        out = marca.og(self.p.dir, nav=self.nav)
        with Image.open(out) as im:
            self.assertEqual(im.size, (1200, 630))
            self.assertEqual(im.convert("RGB").getpixel((600, 620)), (0x9A, 0x4B, 0x1C), "la banda del color corporativo")
        self.assertEqual(marca.og_problemas(out), [])
        self.assertEqual(self.nav.peticiones, [], "nada sale a Internet")
        self.assertEqual(self.nav.consola, [])

    def test_kit_completo(self):
        zp = marca.kit(self.p.dir, nav=self.nav)
        ent = self.p.dir / "marca" / "entrega"
        nombres = set(zipfile.ZipFile(zp).namelist())
        for f in ("logo/logo.svg", "logo/logo.pdf", "logo/logo-600.png", "logo/logo-1200.png", "logo/logo-negativo.pdf", "favicon.svg",
                  "redes/avatar-1080.png", "redes/compartir-1200x630.png", "fuentes/Fraunces-Regular.ttf", "fuentes/Fraunces-Bold.ttf",
                  "fuentes/fraunces-LICENSE.txt", "manual.html", "manual.pdf", "LEEME.txt"):
            self.assertIn(f, nombres)
        pdf = (ent / "logo" / "logo.pdf").read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertNotIn(b"/Subtype /Image", pdf, "el PDF del logo es vectorial, sin imágenes")
        with Image.open(ent / "logo" / "logo-600.png") as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.getpixel((0, 0))[3], 0, "fondo transparente")
            self.assertEqual(im.width, 600)
        with Image.open(ent / "redes" / "avatar-1080.png") as im:
            self.assertEqual(im.size, (1080, 1080))
            self.assertEqual(im.convert("RGB").getpixel((5, 5)), (0xFB, 0xF7, 0xF2), "fondo de la marca, sin transparencias")
        from fontTools.ttLib import TTFont

        for estilo, peso in (("Regular", 400), ("Bold", 700)):
            ft = TTFont(ent / "fuentes" / f"Fraunces-{estilo}.ttf")
            self.assertEqual((ft["name"].getDebugName(1), ft["name"].getDebugName(2), ft["OS/2"].usWeightClass), ("Fraunces", estilo, peso))
            self.assertNotIn("fvar", ft)
            self.assertIsNone(ft.flavor)
        man = (ent / "manual.html").read_text(encoding="utf-8")
        self.assertIn("Manual de marca de Panadería La Espiga", man)
        self.assertNotIn("<text", man)
        self.assertIn("No usar", man, "las combinaciones que no se leen")
        self.assertIn("C0 M51 Y82 K40 (aprox.)", man)
        self.assertEqual(self.nav.peticiones, [])
        self.assertEqual(self.nav.consola, [])

    def test_kit_se_para_si_algo_falla(self):
        (self.p.dir / "static" / "img" / "logo.svg").write_text(OK_SVG.replace("</svg>", "<text>La</text></svg>"))
        with self.assertRaises(SystemExit) as c:
            marca.kit(self.p.dir, nav=self.nav)
        self.assertIn("texto sin convertir", str(c.exception))
        self.assertFalse((self.p.dir / "marca" / "entrega").exists())
        shutil.copy(ROOT / "tests" / "datos" / "demo" / "static" / "img" / "logo.svg", self.p.dir / "static" / "img" / "logo.svg")
        mj = self.p.dir / "marca" / "marca.json"
        mj.write_text(mj.read_text(encoding="utf-8").replace('"lema": "', '"lema": "[CONFIRMAR: lema] '), encoding="utf-8")
        with self.assertRaises(SystemExit) as c:
            marca.kit(self.p.dir, nav=self.nav)
        self.assertIn("[CONFIRMAR]", str(c.exception))
        shutil.copy(ROOT / "tests" / "datos" / "demo" / "marca" / "marca.json", mj)
        self.p.cfg(muted="#B9AFA6")
        with self.assertRaises(SystemExit) as c:
            marca.kit(self.p.dir, nav=self.nav)
        self.assertIn("contraste", str(c.exception))
        self.p.cfg(muted="#6E6158")
        (self.p.dir / "marca" / "logo-negativo.svg").write_text(OK_SVG.replace("<path", '<image href="x.png"/><path'))
        with self.assertRaises(SystemExit) as c:
            marca.kit(self.p.dir, nav=self.nav)
        self.assertIn("marca/logo-negativo.svg", str(c.exception))

    def test_fuente_con_nombre_reservado_no_se_convierte(self):
        lic = self.p.dir / "static" / "fonts" / "fraunces-LICENSE.txt"
        lic.write_text('Copyright 2026 Autor, with Reserved Font Name "Fraunces".\n\n' + lic.read_text(encoding="utf-8"), encoding="utf-8")
        marca.kit(self.p.dir, nav=self.nav)
        fuentes = sorted(p.name for p in (self.p.dir / "marca" / "entrega" / "fuentes").iterdir())
        self.assertEqual(fuentes, ["fraunces-LICENSE.txt"])
        self.assertIn("reserva el nombre", (self.p.dir / "marca" / "entrega" / "LEEME.txt").read_text(encoding="utf-8"))

    def test_manual_escapa_lo_que_viene_de_marca_json(self):
        mj = self.p.dir / "marca" / "marca.json"
        d = json.loads(mj.read_text(encoding="utf-8"))
        d["lema"] = "<script>alert(1)</script>"
        mj.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        man = marca.manual_html(self.p.dir)
        self.assertNotIn("<script>alert", man)
        self.assertIn("&lt;script&gt;", man)

    @unittest.skipUnless(HAS_AXE, "falta axe-core (npm ci)")
    def test_manual_accesible(self):
        import axe

        man = marca.manual_html(self.p.dir, [("logo/logo.svg", "Logo")])
        (self.p.dir / "manual.html").write_text(man, encoding="utf-8")
        srv, base = axe.serve(self.p.dir)
        try:
            found = axe.run([base + "/manual.html"], browser=self.nav.browser) + axe.run([base + "/manual.html"], viewport=(320, 800), browser=self.nav.browser)
        finally:
            srv.shutdown()
        self.assertEqual(found, [])


@unittest.skipUnless(HAS_PW, "falta Playwright")
class CabeceraMovil(unittest.TestCase):
    """Un logo alargado a 320 px: sin scroll horizontal, sin pisar el menú y sin deformarse. Un SVG se encaja solo (preserveAspectRatio);
    un PNG necesita object-fit: contain."""

    def caso(self, nombre: str, datos: bytes):
        s = Site(products=PRODUCTS)
        try:
            (s.dir / "static" / "img" / nombre).write_bytes(datos)
            cfg = json.loads((s.dir / "site.json").read_text(encoding="utf-8"))
            cfg["brand"]["logo"] = f"img/{nombre}"
            (s.dir / "site.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(s.build()[0], 0)
            sys.path.insert(0, str(ROOT / "tools"))
            import axe

            srv, base = axe.serve(s.dir / "public")
            try:
                with sync_playwright() as pw:
                    b = pw.chromium.launch()
                    page = b.new_page(viewport={"width": 320, "height": 700})
                    page.goto(base + "/")
                    ancho = page.evaluate("document.documentElement.scrollWidth")
                    caja = page.locator("img.logo").bounding_box()
                    menu = page.locator(".nav-toggle summary").bounding_box()
                    png = page.screenshot(clip=caja)
                    b.close()
            finally:
                srv.shutdown()
            self.assertLessEqual(ancho, 320, "sin scroll horizontal")
            self.assertLessEqual(caja["x"] + caja["width"], menu["x"], "el logo no pisa el menú")
            self.assertLessEqual(menu["x"] + menu["width"], 320, "el botón del menú se ve entero")
            with Image.open(io.BytesIO(png)) as im:  # el logo (una banda de 15:1) ocupa solo el centro de su caja, no toda la altura
                rgb = im.convert("RGB")
                w, h = rgb.size
                self.assertEqual(rgb.getpixel((w // 2, h // 2)), (0x9A, 0x4B, 0x1C))
                self.assertNotEqual(rgb.getpixel((w // 2, 1)), (0x9A, 0x4B, 0x1C), "estirado a lo alto de la caja: deformado")
        finally:
            s.cleanup()

    @unittest.skipUnless(HAS_PIL, "falta Pillow")
    def test_logo_svg_alargado(self):
        self.caso("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 60"><path fill="#9A4B1C" d="M0 0h900v60H0z"/></svg>')

    @unittest.skipUnless(HAS_PIL, "falta Pillow")
    def test_logo_png_alargado(self):
        buf = io.BytesIO()
        Image.new("RGB", (900, 60), (0x9A, 0x4B, 0x1C)).save(buf, "PNG")
        self.caso("logo-ancho.png", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
