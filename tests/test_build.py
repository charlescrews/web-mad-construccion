"""Tests de build.py: se genera una copia de la plantilla en una carpeta temporal con distintos site.json.

    python -m unittest discover -s tests -t . -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCTS = [
    {"sku": "hogaza", "name": "Hogaza de trigo", "description": "Masa madre.\n\nSegundo párrafo.", "category": "panes",
     "price_cents": 450, "image": "", "attrs": {"formato": "1 kg", "alergenos": ["gluten"]}, "disponible": True},
    {"sku": "agotado", "name": "Pan agotado", "description": "", "category": "panes", "price_cents": 1234567,
     "image": "", "attrs": {}, "disponible": False},
    {"sku": "suelto", "name": "Sin categoría", "description": "", "category": None, "price_cents": 100, "image": "", "attrs": {}},
]


DEMO = ROOT / "tests" / "datos" / "demo"


class Site:
    """Copia de la plantilla con un site.json modificado; build() devuelve (código, salida)."""

    def __init__(self, catalog: dict | None = None, products: list | None = None, **cfg):
        self.dir = Path(tempfile.mkdtemp(prefix="plantilla-a-"))
        for name in ("build.py", "site.json", "content", "static", "tools"):
            # Código del proyecto (build.py, tools/) sobre la demo de la plantilla (tests/datos/demo): los tests no dependen del
            # contenido del cliente, que sustituye a la demo en cada proyecto.
            src = (ROOT if name in ("build.py", "tools") else DEMO) / name
            (shutil.copytree if src.is_dir() else shutil.copy)(src, self.dir / name)
        # Los estilos y scripts de static/ también son código de la plantilla: los del proyecto, no los de la copia de la demo.
        for code in (ROOT / "static").glob("*"):
            if code.suffix in (".css", ".js"):
                shutil.copy(code, self.dir / "static" / code.name)
        site = json.loads((self.dir / "site.json").read_text(encoding="utf-8"))
        site.update(cfg)
        if products is not None:
            (self.dir / "data").mkdir()
            (self.dir / "data" / "cat.json").write_text(json.dumps({"categorias": [{"slug": "panes", "name": "Panes", "sort": 0}],
                                                                    "productos": products}), encoding="utf-8")
        site["catalog"] = {"source": "data/cat.json" if products is not None else "", "page": "productos", **(catalog or {})}
        (self.dir / "site.json").write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")

    def build(self, env: dict | None = None):
        r = subprocess.run([sys.executable, "build.py"], cwd=self.dir, capture_output=True, text=True, env={**os.environ, **(env or {})})
        return r.returncode, r.stdout + r.stderr

    def check(self, env: dict | None = None):
        r = subprocess.run([sys.executable, "tools/check.py"], cwd=self.dir, capture_output=True, text=True, env={**os.environ, **(env or {})})
        return r.returncode, r.stdout + r.stderr

    def read(self, rel: str) -> str:
        return (self.dir / "public" / rel).read_text(encoding="utf-8")

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, *a, **k) -> Site:
        s = Site(*a, **k)
        self.sites.append(s)
        return s

    def test_listado_fichas_jsonld_y_sitemap(self):
        s = self.site(products=PRODUCTS)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertIn("catálogo: 3 productos", out)
        listing = s.read("productos/index.html")
        self.assertIn('data-sku="hogaza"', listing)
        self.assertIn("4,50 €", listing)
        self.assertIn("12.345,67 €", listing, "miles con punto y decimales con coma")
        self.assertIn('id="cat-panes"', listing)
        self.assertIn(">Otros<", listing, "los productos sin categoría van al final")
        self.assertIn('<script src="/catalogo.js" defer>', listing)
        ficha = s.read("productos/hogaza/index.html")
        self.assertEqual(ficha.count("<h1>"), 1)
        self.assertIn("<p>Masa madre.</p><p>Segundo párrafo.</p>", ficha)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', ficha).group(1))
        self.assertEqual(ld["@type"], "Product")
        self.assertEqual(ld["offers"]["price"], "4.50")
        self.assertEqual(ld["offers"]["availability"], "https://schema.org/InStock")
        self.assertIn("OutOfStock", s.read("productos/agotado/index.html"))
        self.assertNotIn("<form class=\"buy\"", ficha, "sin API no hay botón de compra")
        self.assertIn("/productos/hogaza/", s.read("sitemap.xml"))
        self.assertFalse((s.dir / "public" / "en" / "products" / "hogaza").exists(), "sin bloque :::catalogo en inglés, no hay fichas en inglés")
        code, out = s.check()
        self.assertEqual(code, 0, out)

    def test_lo_que_llega_del_catalogo_se_escapa(self):
        evil = dict(PRODUCTS[0], sku="evil", name='<img src=x onerror=alert(1)> </script><script>alert(2)</script>',
                    description='<script>alert(3)</script>\n[enlace](javascript:alert(4))')
        s = self.site(products=[evil])
        code, out = s.build()
        self.assertEqual(code, 0, out)
        for page in ("productos/index.html", "productos/evil/index.html"):
            html = s.read(page)
            self.assertNotIn("<img src=x", html)
            self.assertNotIn("<script>alert", html)
            self.assertNotIn('href="javascript:', html, "la descripción no se interpreta como Markdown")
        ficha = s.read("productos/evil/index.html")
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', ficha, re.S).group(1)
        self.assertNotIn("</script>", ld)
        self.assertEqual(json.loads(ld)["name"], evil["name"], "el JSON-LD sigue siendo válido")

    def test_datos_no_validos_detienen_la_generacion(self):
        bad_cases = [
            dict(PRODUCTS[0], sku="../../fuera"),
            dict(PRODUCTS[0], sku="Con Mayusculas"),
            dict(PRODUCTS[0], sku="categoria"),
            dict(PRODUCTS[0], image="javascript:alert(1)"),
            dict(PRODUCTS[0], image="img/../../secreto.png"),
            dict(PRODUCTS[0], price_cents="4,50"),
            dict(PRODUCTS[0], price_cents=0),
            dict(PRODUCTS[0], name=""),
        ]
        for bad in bad_cases:
            with self.subTest(bad=bad):
                s = self.site(products=[bad])
                code, out = s.build()
                self.assertNotEqual(code, 0, f"debería fallar: {bad}")
                self.assertIn("catálogo con datos no válidos", out)
                self.assertFalse((s.dir.parent / "fuera").exists())
        s = self.site(products=[PRODUCTS[0], dict(PRODUCTS[0])])
        self.assertNotEqual(s.build()[0], 0, "SKU repetido")

    def test_foto_que_falta_no_bloquea_la_publicacion(self):
        s = self.site(products=[dict(PRODUCTS[0], image="img/productos/nueva.webp")])
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertIn("falta static/img/productos/nueva.webp", out)
        self.assertNotIn("nueva.webp", s.read("productos/hogaza/index.html"))
        self.assertEqual(s.check()[0], 0)

    def test_catalogo_vacio_o_inaccesible_no_se_publica(self):
        s = self.site(products=[])
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("está vacío", out)
        s = self.site(products=[], catalog={"permitir_vacio": True})
        self.assertEqual(s.build()[0], 0)
        s = self.site(catalog={"source": "https://127.0.0.1:9/api/catalogo/export.json"})
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("no se pudo descargar", out)
        s = self.site(catalog={"source": "http://api.ejemplo.es/export.json"})
        self.assertIn("https", s.build()[1])
        s = self.site(catalog={"source": "../fuera.json"})
        self.assertNotEqual(s.build()[0], 0)

    def test_compra_privacidad_y_area_de_cliente(self):
        s = self.site(products=PRODUCTS, catalog={"api": "https://api.cliente.es", "comprar": True,
                                                  "envio": [{"id": "recogida", "nombre": "Recogida"}, {"id": "envio", "nombre": "Envío"}]},
                      cuenta_url="https://api.cliente.es/cuenta/entrar")
        code, out = s.build()
        self.assertEqual(code, 0, out)
        ficha = s.read("productos/hogaza/index.html")
        self.assertIn('<form class="buy" action="https://api.cliente.es/api/checkout" method="post">', ficha)
        self.assertIn('name="sku" value="hogaza"', ficha)
        self.assertIn('<select name="envio">', ficha)
        self.assertIn('data-api="https://api.cliente.es"', ficha)
        self.assertNotIn('name="fac_nif"', ficha, "sin factura_completa no hay campos fiscales")
        s2 = self.site(products=PRODUCTS, catalog={"api": "https://api.cliente.es", "comprar": True, "factura_completa": True})
        self.assertEqual(s2.build()[0], 0)
        ficha2 = s2.read("productos/hogaza/index.html")
        for f in ("fac_nif", "fac_nombre", "fac_direccion", "fac_cp", "fac_ciudad"):
            self.assertIn(f'name="{f}"', ficha2)
        self.assertRegex(s.read("productos/agotado/index.html"), r'<button class="btn" type="submit" disabled>')
        privacidad = s.read("privacidad/index.html")
        self.assertIn("<strong>Compras.</strong>", privacidad)
        self.assertIn("api.cliente.es", privacidad)
        self.assertIn("cookie técnica", privacidad)
        self.assertIn('href="https://api.cliente.es/cuenta/entrar"', s.read("index.html"))

    def test_por_categoria(self):
        s = self.site(products=PRODUCTS, catalog={"por_categoria": True})
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertIn('href="/productos/categoria/panes/"', s.read("productos/index.html"))
        self.assertIn('data-sku="hogaza"', s.read("productos/categoria/panes/index.html"))
        self.assertIn("/productos/categoria/panes/", s.read("sitemap.xml"))
        self.assertEqual(s.check()[0], 0, s.check()[1])

    def test_sin_catalogo_la_web_es_la_de_siempre(self):
        s = self.site()
        (s.dir / "content" / "es" / "productos.md").write_text("---\ntitle: Productos\ndescription: x\nnav: 10\n---\n\nTexto.\n", encoding="utf-8")
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertNotIn("catalogo.js", s.read("productos/index.html"))
        s2 = self.site()
        code, out = s2.build()
        self.assertNotEqual(code, 0, "bloque :::catalogo sin catálogo configurado")


class FrontMatterTests(unittest.TestCase):
    def test_valores_entre_comillas_como_los_guarda_un_cms(self):
        s = Site()
        try:
            (s.dir / "content" / "es" / "sobre.md").write_text(
                '---\ntitle: "Quiénes somos: \\"La Espiga\\""\ndescription: \'Panadería de barrio\'\nnav: 20\n---\n\nHola.\n', encoding="utf-8")
            (s.dir / "content" / "es" / "productos.md").write_text("---\ntitle: Productos\ndescription: x\n---\n\nTexto.\n", encoding="utf-8")
            code, out = s.build()
            self.assertEqual(code, 0, out)
            html = s.read("sobre/index.html")
            self.assertIn("<h1>Quiénes somos: &quot;La Espiga&quot;</h1>", html)
            self.assertIn('content="Panadería de barrio"', html)
        finally:
            s.cleanup()


if __name__ == "__main__":
    unittest.main()
