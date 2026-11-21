"""Migraciones (skill plataformas-existentes-cliente): redirecciones de site.json y tools/importar_wordpress.py.

Cada protección tiene su test: destinos solo de esta web, sin cadenas ni páginas tapadas, nada que se cuele en .htaccess,
solo contenido publicado, sin datos personales y sin HTML en lo importado.
"""
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.test_build import PRODUCTS, ROOT, Site

WXR = ROOT / "tests" / "datos" / "wordpress-ejemplo.xml"
_spec = importlib.util.spec_from_file_location("importar_wordpress", ROOT / "tools" / "importar_wordpress.py")
imp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(imp)
_spec2 = importlib.util.spec_from_file_location("axe_tool", ROOT / "tools" / "axe.py")
axe_tool = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(axe_tool)


def redir(reglas: dict, htaccess: bool = False) -> dict:
    return {"redirecciones": {"htaccess": htaccess, "reglas": reglas}}


class Redirecciones(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, **cfg) -> Site:
        s = Site(products=PRODUCTS, **cfg)
        self.sites.append(s)
        return s

    def test_paginas_de_redireccion_canonical_y_fuera_del_sitemap(self):
        s = self.site(**redir({"/quienes-somos/": "@sobre", "/2024/05/vieja-entrada": "@masa-madre", "/contacto.html": "/contacto/#contacto"}))
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertIn("3 redirecciones", out)
        h = s.read("quienes-somos/index.html")
        self.assertIn('<meta http-equiv="refresh" content="0; url=/sobre/">', h)
        self.assertIn('<link rel="canonical" href="https://www.ejemplo-cliente.es/sobre/">', h)
        self.assertIn('content="noindex"', h)
        self.assertIn('<a href="/sobre/">', h, "enlace visible por si el navegador no redirige")
        self.assertTrue((s.dir / "public" / "2024" / "05" / "vieja-entrada" / "index.html").exists())
        self.assertIn("url=/contacto/#contacto", s.read("contacto.html"))
        self.assertNotIn("quienes-somos", s.read("sitemap.xml"))
        self.assertFalse((s.dir / "public" / ".htaccess").exists(), "sin htaccess: true no se escribe")
        code, out = s.check()
        self.assertEqual(code, 0, out)
        urls = axe_tool.pages(s.dir / "public")
        self.assertNotIn("/quienes-somos/", urls, "axe no se pasa en páginas que se van solas")
        self.assertIn("/sobre/", urls)

    def test_htaccess_con_301_y_parametros(self):
        s = self.site(**redir({"/?p=12": "/blog/masa-madre-en-casa/", "/tienda/index.php": "@productos", "/sobre-nosotros/": "/sobre/",
                               "/caf%C3%A9-y-pan/": "/"}, htaccess=True))
        code, out = s.build()
        self.assertEqual(code, 0, out)
        ht = s.read(".htaccess")
        self.assertIn("RewriteCond %{QUERY_STRING} ^p=12$\nRewriteRule ^$ /blog/masa-madre-en-casa/ [R=301,L,NE,QSD]", ht)
        self.assertIn(r"RewriteRule ^tienda/index\.php$ /productos/ [R=301,L,NE,QSD]", ht)
        self.assertIn("RewriteRule ^sobre\\-nosotros/?$ /sobre/ [R=301,L,NE,QSD]", ht)
        self.assertIn("RewriteRule ^café\\-y\\-pan/?$ / [R=301,L,NE,QSD]", ht, "mod_rewrite compara la ruta ya decodificada")
        self.assertFalse((s.dir / "public" / "tienda" / "index.php").exists())

    def test_reglas_que_no_se_aceptan(self):
        malas = [
            ({"/vieja/": "https://otra-web.test/"}, "nunca otro dominio"),
            ({"/vieja/": "//otra-web.test/x"}, "nunca otro dominio"),
            ({"/": "/sobre/"}, "nunca la portada"),
            ({"/x%0ARewriteRule .* https://malo.test [R]": "/sobre/"}, "origen no válido"),
            ({"/x%0Ay/": "/sobre/"}, "origen no válido"),
            ({"/x\ny/": "/sobre/"}, "origen no válido"),
            ({"/vieja/": "/sobre/\nRewriteRule"}, "destino no válido"),
            ({"/a/../b/": "/sobre/"}, "origen no válido"),
            ({"/vieja/": "/no-existe/"}, "que no existe en la web"),
            ({"/a/": "/b/", "/b/": "/sobre/"}, "Sin cadenas"),
            ({"/sobre/": "/contacto/"}, "la redirección la taparía"),
            ({"/vieja/": "/vieja"}, "a sí misma"),
            ({"/?p=12": "/sobre/"}, "solo se puede redirigir con .htaccess"),
            ({"/tienda/index.php": "/sobre/"}, "solo se puede redirigir con .htaccess"),
            ({"/vieja/": "@no-existe"}, "sin página"),
        ]
        for reglas, msg in malas:
            with self.subTest(reglas=reglas):
                s = self.site(**redir(reglas))
                code, out = s.build()
                self.assertNotEqual(code, 0, out)
                self.assertIn(msg, out)


class ImportarWordPress(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wxr-"))
        self.out = self.tmp / "migracion"
        self.r = imp.run(WXR, self.out)
        self.todo = "\n".join(p.read_text(encoding="utf-8") for p in self.out.rglob("*") if p.is_file())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_solo_lo_publicado_y_sin_datos_personales(self):
        self.assertEqual((self.r["entradas"], self.r["paginas"], self.r["omitidas"]), (2, 1, 3))
        for privado in ("Precios internos", "Turnos del personal", "Solo para mayoristas", "mayorista2024"):
            self.assertNotIn(privado, self.todo, "borradores, privadas y con contraseña no se importan")
        for personal in ("autora@web-antigua.test", "comentarista@correo.test", "203.0.113.77", "600123123", "Cliente Comentarista", "autora-ejemplo"):
            self.assertNotIn(personal, self.todo, "ni comentarios ni autores")
        self.assertEqual(sorted(p.name for p in (self.out / "blog").iterdir()), ["como-hacemos-el-pan.md", "el-agua.md"])

    def test_sin_html_ni_enlaces_peligrosos(self):
        md = (self.out / "blog" / "como-hacemos-el-pan.md").read_text(encoding="utf-8")
        body = md.split("---\n", 2)[2]
        self.assertNotRegex(body, r"<\s*(script|iframe|img|a|form)\b", "el resultado es Markdown, sin etiquetas")
        self.assertNotIn("onerror", md)
        self.assertNotIn("javascript:", md)
        self.assertNotIn("document.write", md)
        self.assertNotIn("contact-form-7", body)
        self.assertIn("&lt;script&gt;", body, "lo que era texto sigue siendo texto")
        self.assertNotRegex(body, r"(?m)^:::", "un texto con ::: no abre un bloque de la plantilla")
        self.assertIn("&#58;::hero esto no es un bloque", body)
        self.assertIn("1984\\. Abrimos", body, "no se convierte en lista")
        self.assertIn("[quiénes somos](/nosotros/)", body, "enlaces internos a la dirección nueva")
        self.assertIn("[del grifo](/blog/el-agua/)", body)
        self.assertIn("[Ver el vídeo en YouTube](https://www.youtube.com/watch?v=abc123)", body)
        self.assertIn("\\[CONFIRMAR: texto alternativo de la imagen horno\\]", body)
        self.assertIn('title: "Cómo hacemos el pan: «masa madre» & paciencia"', md)
        pagina = (self.out / "paginas" / "nosotros.md").read_text(encoding="utf-8")
        self.assertIn("## Quiénes somos", pagina, "el h1 del contenido baja a h2")
        self.assertRegex(pagina, r"(?m)^### El equipo$", "sin saltos de nivel (h2 → h3, no h4)")

    def test_redirecciones_imagenes_e_informe(self):
        red = json.loads((self.out / "redirecciones.json").read_text(encoding="utf-8"))
        self.assertEqual(red["reglas"], {"/2024/05/como-hacemos-el-pan/": "/blog/como-hacemos-el-pan/", "/2024/06/el-agua/": "/blog/el-agua/"})
        self.assertEqual(red["solo_htaccess"]["/?page_id=2"], "/nosotros/")
        imgs = (self.out / "imagenes.csv").read_text(encoding="utf-8")
        self.assertIn("hogaza-1024x768.jpg,/img/blog/hogaza.webp", imgs)
        inf = (self.out / "informe.md").read_text(encoding="utf-8")
        self.assertIn("tipo product (no se importa): 1", inf)
        self.assertIn("imagen sin texto alternativo: horno", inf)

    def test_no_pisa_una_migracion_a_medias(self):
        with self.assertRaises(ValueError):
            imp.run(WXR, self.out)
        imp.run(WXR, self.out, overwrite=True)

    def test_rechaza_xml_con_entidades(self):
        bomba = self.tmp / "bomba.xml"
        bomba.write_text('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]><rss><channel>&b;</channel></rss>')
        with self.assertRaises(ValueError):
            imp.run(bomba, self.tmp / "otra")

    def test_lo_importado_se_publica_con_la_plantilla_sin_errores(self):
        s = Site(products=PRODUCTS, **redir({**json.loads((self.out / "redirecciones.json").read_text(encoding="utf-8"))["reglas"], "/nosotros/": "@sobre"}))
        try:
            shutil.copy(self.out / "blog" / "como-hacemos-el-pan.md", s.dir / "content" / "es" / "blog")
            shutil.copy(self.out / "blog" / "el-agua.md", s.dir / "content" / "es" / "blog")
            for img in ("hogaza", "horno"):
                (s.dir / "static" / "img" / "blog").mkdir(parents=True, exist_ok=True)
                shutil.copy(s.dir / "static" / "img" / "productos" / "centeno.webp", s.dir / "static" / "img" / "blog" / f"{img}.webp")
            code, out = s.build()
            self.assertEqual(code, 0, out)
            h = s.read("blog/como-hacemos-el-pan/index.html")
            main = h.split("<main", 1)[1]
            self.assertNotIn("<script>document", main)
            self.assertNotIn("<iframe", main)
            self.assertIn("&lt;script&gt;alert", main)
            self.assertIn('href="/blog/el-agua/"', main)
            self.assertIn("url=/blog/como-hacemos-el-pan/", s.read("2024/05/como-hacemos-el-pan/index.html"))
            code, out = s.check()
            self.assertEqual(code, 0, out)
            self.assertIn("[CONFIRMAR", out, "aviso: queda describir una imagen")
            code, out = subprocess_release(s)
            self.assertNotEqual(code, 0, "--release no deja publicar con el texto alternativo pendiente")
        finally:
            s.cleanup()


class ImportarWordPressReal(unittest.TestCase):
    """Ensayo general: exportación REAL de WordPress 7.0 con WooCommerce 10.3 (WP-CLI `wp export`) de una web de pruebas con contenido
    propio: portada estática, aviso legal propio, páginas de WooCommerce, contenido de ejemplo de WordPress, vídeo con el bloque
    «Insertar», galería, comentarios, borradores, privadas, programadas y con contraseña."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wxr-real-"))
        self.out = self.tmp / "migracion"
        self.r = imp.run(ROOT / "tests" / "datos" / "wordpress-7.0-woocommerce.xml", self.out)
        self.inf = (self.out / "informe.md").read_text(encoding="utf-8")
        self.red = json.loads((self.out / "redirecciones.json").read_text(encoding="utf-8"))
        self.todo = "\n".join(p.read_text(encoding="utf-8") for p in self.out.rglob("*") if p.is_file())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def archivos(self):
        return sorted(str(p.relative_to(self.out)) for p in self.out.rglob("*.md") if p.name != "informe.md")

    def test_ni_ejemplo_de_wordpress_ni_paginas_de_sistema_de_woocommerce(self):
        self.assertEqual(self.archivos(), ["blog/abrimos-los-domingos.md", "blog/como-hacemos-el-pan.md", "blog/pan-integral.md",
                                           "blog/video-baguette.md", "paginas/aviso-legal-2.md", "paginas/contacto.md", "paginas/equipo.md",
                                           "paginas/inicio.md", "paginas/quienes-somos.md"])
        self.assertIn("«Hello world!» (contenido de ejemplo de WordPress)", self.inf)
        self.assertIn("«Sample Page» (contenido de ejemplo de WordPress)", self.inf)
        for p in ("Shop", "Cart", "Checkout", "My account"):
            self.assertIn(f"«{p}» (de sistema de WooCommerce", self.inf)
        self.assertNotIn("Your cart is currently empty", self.todo)
        self.assertNotIn("/cart/", json.dumps(self.red))
        self.assertEqual(self.red["solo_htaccess"], {})

    def test_la_portada_va_a_home_y_los_enlaces_a_ella_a_la_raiz(self):
        self.assertRegex(self.inf, r"`paginas/inicio\.md` \(/\): [^\n]*era la portada: su contenido va a content/es/home\.md")
        self.assertNotIn("/inicio/", set(self.red["reglas"].values()))
        xml = (ROOT / "tests" / "datos" / "wordpress-7.0-woocommerce.xml").read_text(encoding="utf-8")
        xml = xml.replace("Más en <a href", 'Vuelve al <a href="https://www.ejemplo-cliente.es/">inicio</a>. Más en <a href', 1)
        (self.tmp / "con-enlace.xml").write_text(xml, encoding="utf-8")
        imp.run(self.tmp / "con-enlace.xml", self.tmp / "otra")
        self.assertIn("Vuelve al [inicio](/).", (self.tmp / "otra" / "blog" / "como-hacemos-el-pan.md").read_text(encoding="utf-8"))

    def test_una_pagina_que_ya_genera_la_plantilla_no_lleva_redireccion(self):
        self.assertNotIn("/aviso-legal/", self.red["reglas"], "/aviso-legal/ ya existe en la web nueva: redirigirla la taparía")
        self.assertIn("la plantilla ya tiene /aviso-legal/ (se genera desde site.json)", self.inf)
        self.assertEqual(self.red["reglas"]["/quienes-somos/equipo/"], "/equipo/")

    def test_el_bloque_insertar_de_youtube_pasa_a_enlace(self):
        md = (self.out / "blog" / "video-baguette.md").read_text(encoding="utf-8")
        self.assertIn("[Ver el vídeo en YouTube](https://www.youtube.com/watch?v=ejemplo)", md)
        self.assertNotRegex(md, r"(?m)^https://www\.youtube")
        self.assertRegex(self.inf, r"`blog/video-baguette\.md` \(/blog/video-baguette/\): [^\n]*vídeo o mapa incrustado → enlace \(Ver el vídeo en YouTube\)")

    def test_descripciones_cortas_se_escriben_a_mano(self):
        md = (self.out / "blog" / "pan-integral.md").read_text(encoding="utf-8")
        self.assertIn('description: "[CONFIRMAR: descripción de 140-160 caracteres; el texto empieza «No. Tampoco.»]"', md)
        self.assertIn("descripción demasiado corta: escribirla", self.inf)
        pan = (self.out / "blog" / "como-hacemos-el-pan.md").read_text(encoding="utf-8")
        self.assertIn('description: "Lo que pasa entre que amasamos y sale la hogaza del horno."', pan, "el extracto se respeta")
        self.assertEqual(imp.summary_text("---\n\n[Ver el vídeo en YouTube](https://y)\n\nTexto de verdad."), "Texto de verdad.")

    def test_sin_datos_personales_y_csv_sin_retornos(self):
        for personal in ("lucia@ejemplo.invalid", "pedro@ejemplo.invalid", "192.0.2.10", "Lucía Prueba", "maria-redaccion", "wapuu@"):
            self.assertNotIn(personal, self.todo)
        self.assertNotIn("\r", (self.out / "imagenes.csv").read_bytes().decode())
        self.assertNotIn("Margen por hogaza", self.todo)
        self.assertNotIn("Tarifas para hostelería", self.todo)

    def test_sobrescribir_no_deja_restos_de_la_importacion_anterior(self):
        viejo = self.out / "paginas" / "cart.md"
        viejo.write_text("de una importación anterior")
        imp.run(ROOT / "tests" / "datos" / "wordpress-7.0-woocommerce.xml", self.out, overwrite=True)
        self.assertFalse(viejo.exists())
        otro = self.out / "notas-mias.txt"
        otro.write_text("x")
        imp.run(ROOT / "tests" / "datos" / "wordpress-7.0-woocommerce.xml", self.out, overwrite=True)
        self.assertTrue(otro.exists(), "solo se borra lo que genera el importador")


def subprocess_release(s: Site):
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


if __name__ == "__main__":
    unittest.main()
