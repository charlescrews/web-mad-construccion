"""Accesibilidad sin navegador: comprobaciones de tools/check.py (tools/a11y.py), contraste del foco y declaración de accesibilidad.

    python -m unittest discover -s tests -t . -v
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from tests.test_build import PRODUCTS, Site

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import a11y  # noqa: E402

SHOP = {"api": "https://api.cliente.es", "comprar": True}
DONE = {"estado": "total", "fecha_evaluacion": "2026-10-18", "problemas": []}


def page(body: str, lang: str = "es", head: str = "") -> str:
    return f'<!doctype html><html lang="{lang}"><head><meta name="viewport" content="width=device-width, initial-scale=1">{head}<title>x</title></head><body><main><h1>Título</h1>{body}</main></body></html>'


class StaticChecks(unittest.TestCase):
    """tools/a11y.py sobre fragmentos: cada regla se ve fallar y pasar."""

    def errs(self, html: str):
        return a11y.check(html, ["es", "en"])

    def assertFails(self, html: str, needle: str):
        e, _ = self.errs(html)
        self.assertTrue(any(needle in x for x in e), f"esperaba «{needle}» en {e}")

    def assertClean(self, html: str):
        e, _ = self.errs(html)
        self.assertEqual(e, [], html)

    def test_idioma(self):
        self.assertFails('<!doctype html><html><head><title>x</title></head><body><main><h1>a</h1></main></body></html>', "sin atributo lang")
        self.assertFails(page("", lang="fr"), "no es uno de los idiomas")
        self.assertClean(page("", lang="en"))

    def test_zoom(self):
        self.assertFails(page("").replace("initial-scale=1", "initial-scale=1, user-scalable=no"), "impide ampliar")
        self.assertFails(page("").replace("initial-scale=1", "initial-scale=1, maximum-scale=1"), "impide ampliar")
        self.assertClean(page("").replace("initial-scale=1", "initial-scale=1, maximum-scale=5"))

    def test_campos_con_etiqueta(self):
        self.assertFails(page('<input name="q">'), "sin etiqueta")
        self.assertFails(page('<select name="s"><option>a</option></select>'), "sin etiqueta")
        self.assertFails(page('<label for="otro">Nombre</label><input id="q" name="q">'), "sin etiqueta")
        self.assertClean(page('<label>Buscar <input name="q"></label><label for="e">Email</label><input id="e" name="e">'
                              '<input name="z" aria-label="Zona"><input type="hidden" name="h"><input type="submit" value="Enviar">'))

    def test_enlaces_y_botones_con_nombre(self):
        self.assertFails(page('<a href="/"><img src="/x.png" alt=""></a>'), "enlace sin texto")
        self.assertFails(page('<a href="/"> </a>'), "enlace sin texto")
        self.assertFails(page('<button type="button"><span aria-hidden="true">×</span></button>'), "<button> sin texto")
        self.assertClean(page('<a href="/"><img src="/x.png" alt="Inicio"></a><a href="/" aria-label="Inicio">🏠</a>'
                              '<a href="/p" tabindex="-1" aria-hidden="true"><img src="/x.png" alt=""></a><button aria-label="Cerrar">×</button>'))

    def test_iframe_tabindex_y_multimedia(self):
        self.assertFails(page('<iframe src="/mapa/"></iframe>'), "sin title")
        self.assertFails(page('<a href="/" tabindex="3">Inicio</a>'), "tabindex positivo")
        self.assertFails(page('<video src="/v.mp4" autoplay controls></video>'), "con sonido")
        self.assertFails(page('<video src="/v.mp4" autoplay muted></video>'), "sin controls")
        self.assertClean(page('<iframe src="/mapa/" title="Mapa"></iframe><a href="/" tabindex="0">Inicio</a><video src="/v.mp4" autoplay muted controls data-sin-voz></video>'))

    def test_video_con_subtitulos(self):
        """Skill fotografia-video-cliente: un vídeo necesita <track kind="captions"> con archivo, o data-sin-voz si no tiene voz [1.2.2]."""
        self.assertFails(page('<video src="/v.mp4" controls></video>'), "sin subtítulos")
        self.assertFails(page('<video src="/v.mp4" controls><track kind="chapters" src="/c.vtt"></video>'), "sin subtítulos")
        self.assertFails(page('<video src="/v.mp4" controls><track kind="captions"></video>'), "sin subtítulos")
        self.assertClean(page('<video src="/v.mp4" controls><track kind="captions" src="/v.es.vtt" srclang="es"></video>'))
        self.assertClean(page('<video controls><source src="/v.mp4"><track src="/v.es.vtt" srclang="es"></video>'))  # subtitles por defecto
        self.assertClean(page('<video src="/v.mp4" controls data-sin-voz></video>'))

    def test_alt_que_es_un_nombre_de_archivo(self):
        for alt in ("IMG_1234.jpg", "DSC0042", "foto", "hero.webp", "image"):
            self.assertFails(page(f'<img src="/x.png" alt="{alt}">'), "nombre de archivo")
        self.assertClean(page('<img src="/x.png" alt="Hogaza de masa madre recién horneada">'))

    def test_encabezados_en_orden_y_con_texto(self):
        self.assertFails(page("<h3>Detalle</h3>"), "salto de encabezado")
        self.assertFails(page("<h2></h2>"), "vacío")
        self.assertClean(page("<h2>Sección</h2><h3>Detalle</h3><h2>Otra</h2><h3>Más</h3>"))

    def test_ids_duplicados(self):
        self.assertFails(page('<p id="a">1</p><p id="a">2</p>'), "id duplicado")

    def test_avisos(self):
        _, w = self.errs(page('<p><a href="/blog/">Leer más</a></p><a href="/carta.pdf">Carta</a><table><tr><td>1</td></tr></table><img src="/x.png" alt="">'))
        joined = "\n".join(w)
        for needle in ("fuera de contexto", "PDF", "tabla sin encabezados", "¿es decorativa?"):
            self.assertIn(needle, joined)


class SiteChecks(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, body: str = "", products=PRODUCTS, **cfg) -> Site:
        s = Site(products=products, **cfg)
        self.sites.append(s)
        if body:
            (s.dir / "content" / "es" / "prueba.md").write_text(f"---\ntitle: Prueba\ndescription: Prueba\n---\n\n{body}\n", encoding="utf-8")
        code, out = s.build()
        self.assertEqual(code, 0, out)
        return s

    def release(self, s: Site):
        r = subprocess.run([sys.executable, "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_la_plantilla_completa_pasa_sin_errores_de_accesibilidad(self):
        s = self.site(catalog=SHOP, medicion={"ga4": "G-TEST12345", "politica_actualizada": "2026-10-01"})
        code, out = s.check()
        self.assertEqual(code, 0, out)
        self.assertNotIn("[1.", out)
        self.assertNotIn("[2.", out)
        self.assertNotIn("[4.", out)

    def test_contenido_editado_que_rompe_la_accesibilidad_para_la_publicacion(self):
        for body, needle in (('<img src="/img/hero.svg" alt="IMG_2041.jpg">', "nombre de archivo"),
                             ("### Ingredientes", "salto de encabezado"),
                             ('<iframe src="/" ></iframe>', "sin title"),
                             ('<form><input name="email"></form>', "sin etiqueta")):
            s = self.site(body)
            code, out = s.check()
            self.assertNotEqual(code, 0, body)
            self.assertIn(needle, out)

    def test_foco_de_una_marca_clara_falla_y_brand_fix_lo_arregla(self):
        s = self.site()
        cfg = json.loads((s.dir / "site.json").read_text(encoding="utf-8"))
        cfg["brand"].update(primary="#F5C518", primary_ink="#2A211B", link="#7A5C00")
        (s.dir / "site.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        s.build()
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("contorno del foco", out)
        subprocess.run([sys.executable, "tools/brand.py", "--fix"], cwd=s.dir, capture_output=True, text=True)
        fixed = json.loads((s.dir / "site.json").read_text(encoding="utf-8"))["brand"]
        self.assertEqual(fixed["primary"], "#F5C518", "el corporativo no se toca")
        self.assertIn(fixed.get("focus"), (fixed["ink"], fixed["link"]), "el foco usa un color de la propia marca, no uno inventado")
        s.build()
        self.assertIn(f"--focus:{fixed['focus']}", s.read("index.html"))
        code, out = s.check()
        self.assertEqual(code, 0, out)

    def test_declaracion_de_accesibilidad_enlazada_en_cada_idioma(self):
        s = self.site(accesibilidad={"estado": "parcial", "fecha_evaluacion": "2026-10-18",
                                     "problemas": [{"que": "El vídeo de la portada no tiene subtítulos", "alternativa": "La receta está escrita debajo",
                                                    "solucion_prevista": "diciembre de 2026"}]})
        es = s.read("accesibilidad/index.html")
        for part in ("parcialmente conforme", "WCAG) 2.2, nivel AA", "El vídeo de la portada no tiene subtítulos", "La receta está escrita debajo",
                     "18 de octubre de 2026", "Ley 11/2023", "10 días laborables"):
            self.assertIn(part, es)
        self.assertIn('href="/accesibilidad/"', s.read("index.html"), "enlace en el pie")
        self.assertIn('href="/en/accessibility/"', s.read("en/index.html"))
        self.assertIn("partially compliant", s.read("en/accessibility/index.html"))

    def test_tienda_explica_como_funciona_el_servicio(self):
        s = self.site(catalog=SHOP, accesibilidad={**DONE, "descripcion_servicio": "Pan y dulces por encargo con recogida en tienda."})
        es = s.read("accesibilidad/index.html")
        self.assertIn("Cómo funciona el servicio", es)
        self.assertIn("Pan y dulces por encargo", es)
        self.assertIn("pasarela de pago", es)
        s2 = self.site(accesibilidad=DONE)
        self.assertNotIn("Cómo funciona el servicio", s2.read("accesibilidad/index.html"), "sin tienda no hace falta")

    def test_entrega_sin_evaluar_o_con_estado_incoherente_falla(self):
        code, out = self.release(self.site())
        self.assertIn("ERROR: site.json: accesibilidad.fecha_evaluacion vacía", out)
        code, out = self.release(self.site(accesibilidad={"estado": "parcial", "fecha_evaluacion": "2026-10-18"}))
        self.assertIn("sin problemas listados", out)
        code, out = self.release(self.site(catalog=SHOP, accesibilidad=DONE))
        self.assertIn("descripcion_servicio vacía", out)
        code, out = self.release(self.site(accesibilidad=DONE))
        self.assertNotIn("accesibilidad.", out)
        for bad, msg in (({"estado": "casi"}, "accesibilidad.estado"), ({"fecha_evaluacion": "18/10/2026"}, "AAAA-MM-DD"),
                         ({"estado": "total", "problemas": [{"que": "x"}]}, "estado «total» con problemas")):
            s = Site(products=PRODUCTS, accesibilidad=bad)
            self.sites.append(s)
            code, out = s.build()
            self.assertNotEqual(code, 0, bad)
            self.assertIn(msg, out)


if __name__ == "__main__":
    unittest.main()
