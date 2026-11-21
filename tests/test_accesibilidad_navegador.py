"""Accesibilidad en un navegador real (Playwright + axe-core): WCAG 2.2 A/AA en todas las páginas, teclado, foco visible y no tapado,
reflujo a 320 px, aviso de cookies y movimiento reducido. Se salta si faltan Playwright o axe-core (npm ci).

    python -m unittest tests.test_accesibilidad_navegador -v
"""
import sys
import unittest
from pathlib import Path

from tests.test_build import PRODUCTS, Site

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import axe  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    HAS_PW = True
except ImportError:
    HAS_PW = False
HAS_AXE = (ROOT / "node_modules" / "axe-core" / "axe.min.js").exists()

FULL = dict(
    catalog={"api": "https://api.cliente.es", "comprar": True, "factura_completa": True,
             "envio": [{"id": "recogida", "nombre": "Recogida en tienda"}, {"id": "envio", "nombre": "Envío a domicilio"}]},
    medicion={"ga4": "G-TEST12345", "meta_pixel": "1234567890", "politica_actualizada": "2026-10-01"},
    crm={"boletin": "https://api.cliente.es/api/boletin", "ofertas_clientes": True, "aviso_version": "v1",
         "programa": {"bases_url": "https://www.ejemplo-cliente.es/bases-programa/"}},
    accesibilidad={"estado": "total", "fecha_evaluacion": "2026-10-18", "descripcion_servicio": "Pan por encargo."},
    whatsapp={"avisos": True, "aviso_version": "v1"},
)
REJECTED = "localStorage.setItem('ltr_consent', JSON.stringify({v: 1, analitica: false, publicidad: false, at: new Date().toISOString()}))"

# Contraste entre dos colores CSS calculados por el navegador (rgb/rgba sobre opaco).
CONTRAST_JS = """([a, b]) => {
  const p = s => s.match(/[\\d.]+/g).slice(0, 3).map(Number);
  const L = c => { const [r, g, b] = c.map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
                   return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const [x, y] = [L(p(a)), L(p(b))].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}"""
# Fondo sobre el que se dibuja algo de un elemento: el contorno del foco va por fuera (outline-offset), así que se mira el del padre.
BG_JS = """el => { let n = el.parentElement; while (n) { const c = getComputedStyle(n).backgroundColor; if (c && !/rgba\\(.*, 0\\)$/.test(c) && c !== 'transparent') return c; n = n.parentElement; }
  return 'rgb(255, 255, 255)'; }"""


@unittest.skipUnless(HAS_PW and HAS_AXE, "faltan Playwright o axe-core (pip install playwright; npm ci)")
class Navegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Site(products=PRODUCTS, **FULL)
        for name, body in (("novedades", ":::boletin\n## Recibe nuestras novedades\nUna vez al mes.\n:::"),
                           ("bases", "Bases del programa."), ("largo", "\n\n".join(f"Párrafo {i} con [un enlace](@home) al final." for i in range(60)))):
            slug = "bases-programa" if name == "bases" else name
            (cls.s.dir / "content" / "es" / f"{name}.md").write_text(f"---\ntitle: {name.capitalize()}\ndescription: x\nslug: {slug}\n---\n\n{body}\n", encoding="utf-8")
        code, out = cls.s.build()
        assert code == 0, out
        (cls.s.dir / "node_modules").symlink_to(ROOT / "node_modules")
        cls.srv, cls.base = axe.serve(cls.s.dir / "public")
        cls.urls = [cls.base + p for p in axe.pages(cls.s.dir / "public")]
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.s.cleanup()

    def ctx(self, rejected=True, **kw):
        c = self.browser.new_context(**kw)
        c.route("**/*", lambda r: r.continue_() if r.request.url.startswith(self.base) else r.abort())
        if rejected:
            c.add_init_script(f"try{{{REJECTED}}}catch(e){{}}")
        self.addCleanup(c.close)
        return c

    def test_axe_sin_incumplimientos_wcag22_en_todas_las_paginas(self):
        found = axe.run(self.urls, local=True, browser=self.browser) + axe.run(
            [self.base + "/", self.base + "/productos/hogaza/", self.base + "/contacto/"], consent="rechazado", viewport=(390, 844), browser=self.browser)
        self.assertEqual(found, [], "\n".join(f"{f['url']} {f['id']}: {f['help']} {f['nodes']}" for f in found))

    def test_saltar_al_contenido_es_lo_primero_y_funciona(self):
        p = self.ctx().new_page()
        p.goto(self.base + "/")
        p.keyboard.press("Tab")
        self.assertEqual(p.evaluate("document.activeElement.className"), "skip")
        self.assertGreater(p.evaluate("document.activeElement.getBoundingClientRect().top"), 0, "visible al recibir el foco")
        p.keyboard.press("Enter")
        p.keyboard.press("Tab")
        inside = p.evaluate("document.getElementById('main').contains(document.activeElement)")
        self.assertTrue(inside, "tras saltar, el siguiente Tab está en el contenido")

    def test_aviso_de_cookies_con_teclado(self):
        p = self.ctx(rejected=False).new_page()
        p.goto(self.base + "/contacto/")
        self.assertEqual(p.evaluate("document.activeElement.dataset.consent"), "accept", "el foco empieza en el aviso")
        p.keyboard.press("Tab")
        self.assertEqual(p.evaluate("document.activeElement.dataset.consent"), "reject")
        p.keyboard.press("Tab")
        p.keyboard.press("Enter")  # Configurar
        self.assertEqual(p.locator(".consent fieldset legend").count(), 1, "las casillas llevan su grupo con nombre")
        p.locator("[data-consent=reject]").focus()
        p.keyboard.press("Enter")
        self.assertEqual(p.locator(".consent").count(), 0)
        self.assertEqual(p.evaluate("document.activeElement.id"), "main", "al cerrar, el foco vuelve al contenido, no se pierde")
        btn = p.locator("[data-consent-open]")
        btn.focus()
        p.keyboard.press("Enter")
        p.locator("[data-consent=save]").focus()
        p.keyboard.press("Enter")
        self.assertTrue(p.evaluate("document.activeElement.hasAttribute('data-consent-open')"), "vuelve al botón que lo abrió")

    def test_el_foco_nunca_queda_tapado_por_la_cabecera_ni_por_el_aviso(self):
        for rejected in (False, True):
            # Movimiento reducido: sin desplazamiento suave, la posición final se puede medir en cada pulsación.
            p = self.ctx(rejected=rejected, viewport={"width": 1024, "height": 700}, reduced_motion="reduce").new_page()
            p.goto(self.base + "/largo/")
            p.evaluate("document.activeElement && document.activeElement.blur()")
            hidden = []
            for key in ["Tab"] * 75 + ["Shift+Tab"] * 75:  # hacia delante (aviso) y hacia atrás (cabecera fija)
                p.keyboard.press(key)
                p.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")  # estilos y foco.js aplicados
                # Al dar la vuelta, el foco pasa por la interfaz del navegador y el documento no lo tiene: no cuenta.
                r = p.evaluate("""() => { const a = document.activeElement; if (!a || a === document.body || !document.hasFocus()) return null;
                  const box = document.querySelector('.consent'); if (box && box.contains(a)) return null;
                  const r = a.getBoundingClientRect(); const x = r.left + r.width / 2, y = r.top + r.height / 2;
                  const top = document.elementFromPoint(x, y);
                  return top && (top === a || a.contains(top)) ? null : (a.textContent || a.tagName).trim().slice(0, 40); }""")
                if r:
                    hidden.append(r)
            self.assertEqual(hidden, [], f"elementos con el foco tapados (aviso {'rechazado' if rejected else 'abierto'})")

    def test_reflujo_a_320_px_sin_desplazamiento_horizontal(self):
        p = self.ctx(viewport={"width": 320, "height": 640}).new_page()
        wide = []
        for u in self.urls:
            p.goto(u)
            if p.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"):
                wide.append(u.replace(self.base, ""))
        self.assertEqual(wide, [], "páginas que obligan a desplazarse en horizontal a 320 px (zoom al 400 %)")

    def tab_to(self, p, loc):
        """Llega al elemento con el teclado (el contorno de :focus-visible solo se ve así)."""
        loc.evaluate("e => { window.__t = e; }")
        for _ in range(250):
            p.keyboard.press("Tab")
            if p.evaluate("document.activeElement === window.__t"):
                return True
        return False

    def test_foco_y_bordes_de_campos_con_contraste_3_a_1(self):
        p = self.ctx().new_page()
        p.goto(self.base + "/contacto/")
        low = []
        for sel in (".site-footer a", ".site-header a", "main a", ".cta .btn"):
            for el in p.locator(sel + " >> visible=true").all()[:2]:
                self.assertTrue(self.tab_to(p, el), sel)
                outline = el.evaluate("e => getComputedStyle(e).outlineColor")
                bg = el.evaluate(BG_JS)
                ratio = p.evaluate(CONTRAST_JS, [outline, bg])
                if ratio < 3:
                    low.append(f"foco {sel}: {ratio:.2f}")
        for el in p.locator("form input:not([type=hidden]):not([type=checkbox]), form textarea, form select").all():
            if not el.is_visible():
                continue
            border = el.evaluate("e => getComputedStyle(e).borderTopColor")
            bg = el.evaluate(BG_JS)
            ratio = p.evaluate(CONTRAST_JS, [border, bg])
            if ratio < 3:
                low.append(f"borde de {el.get_attribute('name')}: {ratio:.2f}")
        self.assertEqual(low, [])

    def test_cta_y_pie_foco_visible(self):
        p = self.ctx().new_page()
        p.goto(self.base + "/")
        for sel in (".cta a", ".site-footer a"):
            loc = p.locator(sel)
            if not loc.count():
                continue
            self.assertTrue(self.tab_to(p, loc.first), sel)
            ratio = p.evaluate(CONTRAST_JS, [loc.first.evaluate("e => getComputedStyle(e).outlineColor"), loc.first.evaluate(BG_JS)])
            self.assertGreaterEqual(ratio, 3, sel)

    def test_buscador_del_catalogo_anuncia_los_resultados(self):
        p = self.ctx().new_page()
        p.goto(self.base + "/productos/")
        live = p.locator(".catalog-count")
        self.assertEqual(live.get_attribute("aria-live"), "polite")
        p.get_by_label("Buscar").fill("hogaza")
        p.wait_for_timeout(400)
        self.assertRegex(live.inner_text(), r"\d")

    def test_movimiento_reducido(self):
        p = self.ctx(reduced_motion="reduce").new_page()
        p.goto(self.base + "/")
        p.add_style_tag(content=".prueba-mov { transition: opacity 2s; animation: x 3s infinite; } @keyframes x { to { opacity: .5 } }")
        p.evaluate("document.querySelector('main').insertAdjacentHTML('beforeend', '<p class=prueba-mov>x</p>')")
        dur = p.evaluate("getComputedStyle(document.querySelector('.prueba-mov')).transitionDuration")
        self.assertIn(dur, ("1e-05s", "0.00001s", "0s"), "con movimiento reducido no hay transiciones ni animaciones")


if __name__ == "__main__":
    unittest.main()
