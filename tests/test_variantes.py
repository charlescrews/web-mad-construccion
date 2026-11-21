"""Variantes de bloque (`:::hero banda`, `:::cards oscuro`, `:::split [inverso]`) y barra fija de contacto en el móvil
(site.json > barra_movil.activa). En el navegador: la barra solo sale en pantallas estrechas y no tapa el foco ni el final del pie.

    python -m unittest tests.test_variantes -v
"""
import shutil
import sys
import unittest
from pathlib import Path

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

PORTADA = """---
key: home
title: Inicio
description: Portada de prueba con variantes de bloque.
---

:::hero banda
# Alicatados en Loja

Texto de la portada.

[Pide presupuesto](@contacto) [Llamar](tel:+34600000001)

![Baño alicatado en blanco](/img/hero.svg)
:::

:::cards oscuro
## Qué hacemos

### Alicatados
Paredes de baños y cocinas.

### Solados
Suelos nivelados.
:::

:::split inverso
![Suelo de baldosa recién colocado](/img/hero.svg)

## Cómo trabajamos

Primero vemos la obra.

[Pide presupuesto](@contacto)
:::

:::split
![Detalle de una esquina](/img/hero.svg)

## Remates

Esquinas y juntas.
:::
"""


def sitio(home=PORTADA, **cfg):
    s = Site(**{"languages": ["es"], **cfg})
    shutil.rmtree(s.dir / "content" / "en")  # un idioma basta para probar las variantes
    (s.dir / "content" / "es" / "home.md").write_text(home, encoding="utf-8")
    for f in s.dir.glob("content/*/productos.md"):
        f.unlink()  # la demo trae catálogo; aquí no hace falta
    return s


class Generacion(unittest.TestCase):
    def build_ok(self, **kw):
        s = sitio(**kw)
        self.addCleanup(s.cleanup)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        return s

    def test_portada_banda_con_foto_de_fondo_y_botones(self):
        h = self.build_ok().read("index.html")
        self.assertIn('<section class="hero hero-banda has-media"><div class="hero-fondo"><img', h)
        self.assertIn('alt="Baño alicatado en blanco"', h)
        self.assertIn('fetchpriority="high"', h.split('class="hero-fondo"')[1][:400])
        self.assertIn('<p class="actions"><a class="btn"', h.split("hero-banda")[1])

    def test_banda_sin_foto_y_hero_normal_sin_cambios(self):
        s = self.build_ok(home=PORTADA.replace("\n![Baño alicatado en blanco](/img/hero.svg)\n", "\n"))
        self.assertIn('<section class="hero hero-banda"><div class="wrap hero-text">', s.read("index.html"))
        normal = self.build_ok(home=PORTADA.replace(":::hero banda", ":::hero")).read("index.html")
        self.assertIn('<section class="hero has-media"><div class="wrap hero-grid">', normal)
        self.assertNotIn("hero-banda", normal)

    def test_tarjetas_sobre_banda_oscura_a_todo_el_ancho(self):
        h = self.build_ok().read("index.html")
        self.assertIn('<section class="section banda-oscura"><div class="wrap"><div class="section-head">', h)
        self.assertEqual(h.count('<div class="card">'), 2)

    def test_imagen_y_texto_en_paralelo(self):
        h = self.build_ok().read("index.html")
        self.assertIn('<section class="section wrap split split-inverso"><div class="split-media"><img', h)
        self.assertIn('<section class="section wrap split"><div class="split-media"><img', h)
        texto = h.split('class="split-text">')[1].split("</section>")[0]
        self.assertIn("<h2", texto)
        self.assertIn('<p class="actions"><a class="btn"', texto)

    def test_split_sin_imagen_o_variante_desconocida_no_se_publica(self):
        for home, msg in ((PORTADA.replace("![Detalle de una esquina](/img/hero.svg)\n", ""), ":::split necesita una imagen"),
                          (PORTADA.replace(":::cards oscuro", ":::cards oscura"), "variante desconocida en :::cards: oscura"),
                          (PORTADA.replace(":::split inverso", ":::split banda"), "variante desconocida en :::split: banda")):
            s = sitio(home=home)
            self.addCleanup(s.cleanup)
            code, out = s.build()
            self.assertNotEqual(code, 0)
            self.assertIn(msg, out)

    def test_composiciones_de_tarjetas(self):
        for mod in ("juntas", "galeria", "comparar"):
            h = self.build_ok(home=PORTADA.replace(":::cards oscuro", f":::cards {mod}")).read("index.html")
            self.assertIn(f'<section class="section wrap section-{mod}"><div class="section-head">', h)
            self.assertIn(f'<div class="cards cards-{mod}"><div class="card">', h)
        oscuro = self.build_ok(home=PORTADA.replace(":::cards oscuro", ":::cards oscuro galeria")).read("index.html")
        self.assertIn('<section class="section banda-oscura">', oscuro)
        self.assertIn('<div class="cards cards-galeria">', oscuro)

    def test_franja_de_datos_sin_cabecera(self):
        home = PORTADA.replace(":::cards oscuro\n## Qué hacemos\n\n", ":::cards datos\n")
        h = self.build_ok(home=home).read("index.html")
        self.assertIn('<section class="section wrap section-datos"><div class="cards cards-datos"><div class="card"><p class="dato">Alicatados</p>', h)
        self.assertNotIn("<h3", h.split("section-datos")[1].split("</section>")[0])  # sin saltos de h1 a h3
        self.assertNotIn('<div class="section-head"></div>', h)

    def test_dos_composiciones_a_la_vez_no_se_publica(self):
        s = sitio(home=PORTADA.replace(":::cards oscuro", ":::cards juntas galeria"))
        self.addCleanup(s.cleanup)
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("dos composiciones a la vez: juntas, galeria", out)

    def test_barra_movil_con_llamar_y_whatsapp(self):
        co = {**_company(), "whatsapp": "+34 600 000 002"}
        h = self.build_ok(company=co, barra_movil={"activa": True}).read("contacto/index.html")
        barra = h.split('<nav class="barra-movil"')[1].split("</nav>")[0]
        self.assertIn('aria-label="Contacto rápido"', barra)
        self.assertIn('href="tel:+34600000001">Llamar</a>', barra)
        self.assertIn('href="https://wa.me/34600000002">WhatsApp</a>', barra)

    def test_barra_movil_sin_whatsapp_solo_llamar_y_desactivada_no_sale(self):
        h = self.build_ok(company=_company(), barra_movil={"activa": True}).read("index.html")
        barra = h.split('<nav class="barra-movil"')[1].split("</nav>")[0]
        self.assertIn(">Llamar</a>", barra)
        self.assertNotIn("wa.me", barra)
        self.assertNotIn("barra-movil", self.build_ok(company=_company()).read("index.html"))

    def test_barra_movil_se_quita_en_una_pagina(self):
        s = sitio(company=_company(), barra_movil={"activa": True})
        self.addCleanup(s.cleanup)
        c = s.dir / "content" / "es" / "contacto.md"
        c.write_text(c.read_text(encoding="utf-8").replace("\n---\n", "\nbarra_movil: false\n---\n", 1), encoding="utf-8")
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertNotIn("barra-movil", s.read("contacto/index.html"))
        self.assertIn('<nav class="barra-movil"', s.read("index.html"), "en las demás páginas sigue")
        c.write_text(c.read_text(encoding="utf-8").replace("barra_movil: false", "barra_movil: no"), encoding="utf-8")
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("barra_movil debe ser true o false", out)

    def test_barra_movil_sin_telefono_no_se_publica(self):
        co = _company()
        co.pop("phone")
        s = sitio(company=co, barra_movil={"activa": True})
        self.addCleanup(s.cleanup)
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("barra_movil.activa sin company.phone", out)


def _company():
    import json
    co = json.loads((ROOT / "tests" / "datos" / "demo" / "site.json").read_text(encoding="utf-8"))["company"]
    co.update({"phone": "+34 600 000 001"})
    co.pop("whatsapp", None)
    return co


@unittest.skipUnless(HAS_PW and HAS_AXE, "faltan Playwright o axe-core (pip install playwright; npm ci)")
class Navegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        largo = "\n\n".join(f"Párrafo {i} con [un enlace](@home)." for i in range(40))
        cls.s = sitio(company={**_company(), "whatsapp": "+34600000002"}, barra_movil={"activa": True})
        (cls.s.dir / "content" / "es" / "largo.md").write_text(f"---\ntitle: Largo\ndescription: x\n---\n\n{largo}\n", encoding="utf-8")
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

    def page(self, w, touch=True):
        # Movimiento reducido: sin desplazamiento suave, la posición final se mide en cada pulsación. Táctil: como un móvil.
        c = self.browser.new_context(viewport={"width": w, "height": 700}, reduced_motion="reduce", has_touch=touch)
        self.addCleanup(c.close)
        p = c.new_page()
        p.route("**/*", lambda r: r.continue_() if r.request.url.startswith(self.base) else r.abort())
        return p

    def test_solo_en_pantallas_estrechas(self):
        p = self.page(360)
        p.goto(self.base + "/")
        self.assertTrue(p.is_visible(".barra-movil"))
        caja = p.locator(".barra-movil").bounding_box()
        self.assertAlmostEqual(caja["y"] + caja["height"], 700, delta=1)
        for a in p.locator(".barra-movil a").all():
            self.assertGreaterEqual(a.bounding_box()["height"], 44, "botones fáciles de pulsar")
        p2 = self.page(1280)
        p2.goto(self.base + "/")
        self.assertFalse(p2.is_visible(".barra-movil"), "tableta o pantalla ancha")

    def test_no_sale_en_un_ordenador_con_la_ventana_estrecha(self):
        # Ratón, no táctil: aunque la ventana (o el panel donde se ve la web) mida lo que un móvil, no es un móvil.
        for w in (360, 700):
            p = self.page(w, touch=False)
            p.goto(self.base + "/")
            self.assertFalse(p.is_visible(".barra-movil"), w)
            self.assertEqual(p.evaluate("getComputedStyle(document.body).paddingBottom"), "0px", "sin hueco reservado para la barra")

    def test_no_tapa_el_foco_al_tabular(self):
        p = self.page(360)
        p.goto(self.base + "/largo/")
        tapados = []
        for key in ["Tab"] * 60 + ["Shift+Tab"] * 60:
            p.keyboard.press(key)
            p.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            r = p.evaluate("""() => { const a = document.activeElement; if (!a || a === document.body || !document.hasFocus()) return null;
                if (a.closest('.barra-movil')) return null;
                const b = a.getBoundingClientRect(), top = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
                return top && (top === a || a.contains(top)) ? null : (a.textContent || a.tagName).trim().slice(0, 30); }""")
            if r:
                tapados.append(r)
        self.assertEqual(tapados, [], "la barra tapa lo que tiene el foco [WCAG 2.4.11]")

    def test_no_tapa_el_final_del_pie(self):
        p = self.page(360)
        p.goto(self.base + "/")
        p.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        abajo = p.evaluate("""() => { const t = document.querySelector('.footer-base p').getBoundingClientRect();
            return [t.bottom, document.querySelector('.barra-movil').getBoundingClientRect().top]; }""")
        self.assertLessEqual(abajo[0], abajo[1] + 1, "el final del pie queda debajo de la barra")

    def test_axe_sin_incumplimientos_con_las_variantes(self):
        for w in (360, 1280):
            found = axe.run([self.base + "/", self.base + "/largo/"], local=True, browser=self.browser, viewport=(w, 800))
            self.assertEqual(found, [], found)


if __name__ == "__main__":
    unittest.main()
