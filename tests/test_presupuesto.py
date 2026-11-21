"""Formulario de presupuesto (bloque :::presupuesto, site.json > presupuesto): prepara un mensaje de WhatsApp o un email con lo que
escribe la persona. La web no envía ni guarda nada; los enlaces funcionan sin JavaScript y el texto va siempre codificado para la URL.

    python -m unittest tests.test_presupuesto -v
"""
import json
import re
import shutil
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from tests.test_build import Site

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import axe  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    HAS_PW = True
except ImportError:
    HAS_PW = False
HAS_AXE = (ROOT / "node_modules" / "axe-core" / "axe.min.js").exists()

PAGINA = """---
key: presupuesto
title: Pide presupuesto
nav: 40
description: Prepara tu solicitud de presupuesto.
---

:::presupuesto
Cuéntanos tu obra y te contestamos.
:::
"""
TRABAJOS = ["Baño", "Cocina", "Suelo", "Otro"]


def company(**over):
    co = json.loads((ROOT / "tests" / "datos" / "demo" / "site.json").read_text(encoding="utf-8"))["company"]
    co.update({"whatsapp": "+34 600 000 002", "email": "hola@cliente-real.es"})
    co.update(over)
    return {k: v for k, v in co.items() if v is not None}


def sitio(pagina=PAGINA, **cfg):
    cfg.setdefault("presupuesto", {"trabajos": TRABAJOS})
    cfg.setdefault("company", company())
    s = Site(**{"languages": ["es"], **cfg})
    shutil.rmtree(s.dir / "content" / "en")
    for f in s.dir.glob("content/*/productos.md"):
        f.unlink()
    (s.dir / "content" / "es" / "home.md").write_text("---\nkey: home\ntitle: Inicio\ndescription: x\n---\n\nPortada.\n", encoding="utf-8")
    (s.dir / "content" / "es" / "presupuesto.md").write_text(pagina, encoding="utf-8")
    return s


class Generacion(unittest.TestCase):
    def build(self, **kw):
        s = sitio(**kw)
        self.addCleanup(s.cleanup)
        return s, *s.build()

    def test_campos_con_etiqueta_enlaces_y_script_solo_en_su_pagina(self):
        s, code, out = self.build()
        self.assertEqual(code, 0, out)
        h = s.read("presupuesto/index.html")
        form = h.split('<form class="contact-form pres-form"')[1].split("</form>")[0]
        for etiqueta in ("¿Qué trabajo es?", "Pueblo o zona de la obra", "Medidas aproximadas", "¿Para cuándo?", "Tu nombre", "Cuéntanos algo más"):
            self.assertRegex(form, rf"<label>(<span>)?{re.escape(etiqueta)}")
        self.assertIn("<option>Baño</option><option>Cocina</option>", form)
        self.assertIn("<option>Lo antes posible</option>", form)
        self.assertIn('href="https://wa.me/34600000002">Enviar por WhatsApp', form)
        self.assertIn('href="mailto:hola@cliente-real.es">Prefiero enviarlo por email', form)
        self.assertIn("no envía ni guarda nada", form)
        self.assertNotIn("action=", form, "el formulario no envía a ningún sitio")
        self.assertIn('<script src="/presupuesto.js" defer></script>', h)
        self.assertNotIn("presupuesto.js", s.read("index.html"))
        priv = s.read("privacidad/index.html")
        self.assertIn("<strong>Formulario de presupuesto.</strong> No envía ni guarda nada en esta web", priv)

    def test_sin_formulario_la_privacidad_no_lo_menciona(self):
        s2 = sitio(presupuesto={"trabajos": [], "plazos": [], "note": "Vacío si no se usa."})
        self.addCleanup(s2.cleanup)
        (s2.dir / "content" / "es" / "presupuesto.md").write_text(PAGINA.replace(":::presupuesto\nCuéntanos tu obra y te contestamos.\n:::", "Texto."), encoding="utf-8")
        code, out = s2.build()
        self.assertEqual(code, 0, out)
        self.assertNotIn("Formulario de presupuesto", s2.read("privacidad/index.html"))

    def test_solo_email_si_no_hay_whatsapp_y_plazos_propios(self):
        s, code, out = self.build(company=company(whatsapp=None), presupuesto={"trabajos": TRABAJOS, "plazos": ["Este mes", "Este año"]})
        self.assertEqual(code, 0, out)
        form = s.read("presupuesto/index.html").split("pres-form")[1].split("</form>")[0]
        self.assertNotIn("wa.me", form)
        self.assertIn('class="btn pres-email" href="mailto:hola@cliente-real.es">Email</a>', form)
        self.assertIn("<option>Este mes</option><option>Este año</option>", form)
        self.assertNotIn("Lo antes posible", form)

    def test_sin_trabajos_o_sin_destino_no_se_publica(self):
        for cfg, msg in (({"presupuesto": {}}, "presupuesto.trabajos"),
                         ({"presupuesto": {"trabajos": ["Baño", ""]}}, "presupuesto.trabajos"),
                         ({"company": company(whatsapp=None, email=None)}, "company.whatsapp o company.email")):
            s, code, out = self.build(**cfg)
            self.assertNotEqual(code, 0, cfg)
            self.assertIn(msg, out)

    def test_trabajos_y_plazos_por_idioma(self):
        s = sitio(presupuesto={"trabajos": {"es": ["Baño", "Cocina"], "en": ["Bathroom", "Kitchen"]},
                               "plazos": {"es": ["Este mes"], "en": ["This month"]}}, languages=["es", "en"])
        self.addCleanup(s.cleanup)
        en = s.dir / "content" / "en"
        en.mkdir()
        (en / "home.md").write_text("---\nkey: home\ntitle: Home\ndescription: x\n---\n\nHome.\n", encoding="utf-8")
        (en / "presupuesto.md").write_text(PAGINA.replace("title: Pide presupuesto", "slug: quote\ntitle: Request a quote"), encoding="utf-8")
        code, out = s.build()
        self.assertEqual(code, 0, out)
        es, en_ = s.read("presupuesto/index.html"), s.read("en/quote/index.html")
        self.assertIn("<option>Baño</option><option>Cocina</option>", es)
        self.assertIn("<option>Este mes</option>", es)
        self.assertIn("<option>Bathroom</option><option>Kitchen</option>", en_)
        self.assertIn("<option>This month</option>", en_)
        self.assertNotIn("Baño", en_.split("pres-form")[1].split("</form>")[0])
        self.assertIn('data-lang="en"', en_)
        self.assertIn("Send on WhatsApp", en_)

    def test_falta_la_lista_de_un_idioma_no_se_publica(self):
        s = sitio(presupuesto={"trabajos": {"es": ["Baño"]}}, languages=["es", "en"])
        self.addCleanup(s.cleanup)
        en = s.dir / "content" / "en"
        en.mkdir()
        (en / "home.md").write_text("---\nkey: home\ntitle: Home\ndescription: x\n---\n\nHome.\n", encoding="utf-8")
        (en / "presupuesto.md").write_text(PAGINA.replace("title: Pide presupuesto", "slug: quote\ntitle: Request a quote"), encoding="utf-8")
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("presupuesto.trabajos para «en»", out)

    def test_texto_del_cliente_escapado_en_el_html(self):
        s, code, out = self.build(presupuesto={"trabajos": ["Baño <b>", "Cocina & salón"]})
        self.assertEqual(code, 0, out)
        h = s.read("presupuesto/index.html")
        self.assertIn("<option>Baño &lt;b&gt;</option><option>Cocina &amp; salón</option>", h)


@unittest.skipUnless(HAS_PW and HAS_AXE, "faltan Playwright o axe-core (pip install playwright; npm ci)")
class Navegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = sitio()
        code, out = cls.s.build()
        assert code == 0, out
        (cls.s.dir / "node_modules").symlink_to(ROOT / "node_modules")
        cls.srv, cls.base = axe.serve(cls.s.dir / "public")
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.s.cleanup()

    def page(self):
        c = self.browser.new_context(viewport={"width": 390, "height": 800})
        self.addCleanup(c.close)
        p = c.new_page()
        self.salidas = []
        # Nada sale de la web: wa.me se intercepta para ver a dónde iría.
        p.route("**/*", lambda r: r.continue_() if r.request.url.startswith(self.base) else (self.salidas.append(r.request.url), r.abort()))
        errores = []
        p.on("pageerror", lambda e: errores.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errores, []))
        p.goto(self.base + "/presupuesto/")
        return p

    def rellenar(self, p, nota="Quitar bañera & poner plato de ducha #2\nUrgente?"):
        p.select_option("select[name=trabajo]", "Baño")
        p.fill("input[name=localidad]", "Loja")
        p.fill("input[name=medidas]", "2 × 3 m")
        p.select_option("select[name=cuando]", "Lo antes posible")
        p.fill("input[name=nombre]", "Ana")
        p.fill("textarea[name=nota]", nota)

    def test_mensaje_de_whatsapp_completo_y_codificado(self):
        p = self.page()
        self.rellenar(p)
        href = p.get_attribute("a.pres-wa", "href")
        u = urlparse(href)
        self.assertEqual((u.scheme, u.netloc, u.path), ("https", "wa.me", "/34600000002"))
        q = parse_qs(u.query)
        self.assertEqual(list(q), ["text"], "lo escrito no crea parámetros nuevos en la URL")
        texto = q["text"][0]
        self.assertEqual(texto.split("\n"), ["Hola, quiero pedir presupuesto.", "Trabajo: Baño", "Pueblo o zona: Loja",
                                              "Medidas aproximadas: 2 × 3 m", "Para cuándo: Lo antes posible", "Nombre: Ana",
                                              "Más detalles: Quitar bañera & poner plato de ducha #2", "Urgente?",
                                              "(Si puedo, te mando fotos por aquí.)"])

    def test_campos_vacios_no_salen_en_el_mensaje(self):
        p = self.page()
        p.fill("input[name=localidad]", "Loja")
        texto = parse_qs(urlparse(p.get_attribute("a.pres-wa", "href")).query)["text"][0]
        self.assertEqual(texto.split("\n"), ["Hola, quiero pedir presupuesto.", "Pueblo o zona: Loja", "(Si puedo, te mando fotos por aquí.)"])

    def test_email_con_asunto_y_cuerpo_codificados(self):
        p = self.page()
        self.rellenar(p, nota="Hola&cc=otro@ejemplo.es")
        href = p.get_attribute("a.pres-email", "href")
        self.assertTrue(href.startswith("mailto:hola@cliente-real.es?"))
        q = parse_qs(href.split("?", 1)[1])
        self.assertEqual(sorted(q), ["body", "subject"], "la nota no añade destinatarios (cc, bcc)")
        self.assertEqual(q["subject"][0], "Presupuesto: Baño (Loja)")
        self.assertIn("Más detalles: Hola&cc=otro@ejemplo.es", q["body"][0])

    def test_intro_en_un_campo_abre_whatsapp_con_el_mensaje(self):
        p = self.page()
        self.rellenar(p)
        p.focus("input[name=localidad]")
        p.keyboard.press("Enter")
        p.wait_for_timeout(300)
        self.assertTrue(any(unquote(u).startswith("https://wa.me/34600000002?text=Hola") for u in self.salidas), self.salidas)

    def test_teclado_y_axe(self):
        p = self.page()
        orden = []
        for _ in range(30):
            p.keyboard.press("Tab")
            orden.append(p.evaluate("document.activeElement.name || document.activeElement.className || ''"))
        for n in ("trabajo", "localidad", "medidas", "cuando", "nombre", "nota", "btn pres-wa", "btn btn-ghost pres-email"):
            self.assertIn(n, orden)
        self.assertEqual(axe.run([self.base + "/presupuesto/"], local=True, browser=self.browser), [])


if __name__ == "__main__":
    unittest.main()
