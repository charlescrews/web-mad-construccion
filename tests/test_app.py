"""Web instalable, avisos en el dispositivo y enlaces con las apps de las tiendas (skill apps-moviles-cliente).

Protecciones con test: sin site.json > app no cambia nada; sin iconos de la medida justa no se publica; el service worker no toca
formularios ni otros dominios, solo guarda lo de la web y se renueva con cada publicación; un aviso solo abre la web o su API; a quien
solo visita la web no se le registra nada; la casilla de avisos viene sin marcar y pide el permiso al marcarla; la baja es igual de fácil;
/.well-known solo con datos válidos y se publica en GitHub Pages; las fichas de las tiendas solo de Apple y Google; la privacidad lo explica.
"""
import base64
import json
import re
import shutil
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

from tests.test_build import PRODUCTS, ROOT, Site

try:
    from playwright.sync_api import sync_playwright
    HAS_PW = True
except ImportError:
    HAS_PW = False

try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Clave pública VAPID de ejemplo (un punto P-256 válido, sin comprimir).
KEY = "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
BUY = {"api": "https://api.cliente.es", "comprar": True}
FP = ":".join(["AB"] * 32)


def png(path: Path, w: int, h: int, rgb=(154, 75, 28)) -> None:
    """PNG de un color, sin Pillow (los tests no dependen de él)."""
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)  # noqa: E731
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def icons(s: Site, skip: str = "", wrong: str = "") -> None:
    for rel, side in (("app/icono-192.png", 192), ("app/icono-512.png", 512), ("app/icono-maskable-512.png", 512), ("app/apple-touch-icon.png", 180)):
        if rel != skip:
            png(s.dir / "static" / rel, side + (8 if rel == wrong else 0), side)


def app_cfg(**over) -> dict:
    a = {"pwa": True, "nombre": "Panadería La Espiga", "nombre_corto": "La Espiga", "push": {}, "tiendas": {}, "ios": {}, "android": {}}
    a.update(over)
    return a


class App(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, with_icons=True, **cfg) -> Site:
        cfg.setdefault("products", PRODUCTS)
        s = Site(**cfg)
        self.sites.append(s)
        if with_icons:
            icons(s)
        return s

    def ok(self, s: Site) -> str:
        code, out = s.build()
        self.assertEqual(code, 0, out)
        return out

    def test_sin_app_nada_cambia(self):
        s = self.site(with_icons=False)
        self.ok(s)
        pub = s.dir / "public"
        for f in ("manifest.webmanifest", "sw.js", "app.js", ".well-known", "sin-conexion"):
            self.assertFalse((pub / f).exists(), f)
        home = s.read("index.html")
        self.assertNotIn("manifest", home)
        self.assertNotIn("apple-itunes-app", home)
        self.assertNotIn("Web instalable", s.read("privacidad/index.html"))

    def test_web_instalable_manifiesto_iconos_y_sin_conexion(self):
        s = self.site(app=app_cfg())
        out = self.ok(s)
        self.assertIn("app: manifest.webmanifest, sw.js", out)
        m = json.loads(s.read("manifest.webmanifest"))
        self.assertEqual((m["id"], m["start_url"], m["scope"], m["display"], m["lang"]), ("/", "/", "/", "standalone", "es"))
        self.assertEqual(m["short_name"], "La Espiga")
        self.assertEqual(m["theme_color"], "#9A4B1C")
        self.assertEqual({i["purpose"] for i in m["icons"]}, {"any", "maskable"})
        for i in m["icons"]:
            self.assertTrue((s.dir / "public" / i["src"].lstrip("/")).is_file(), i["src"])
        for page in sorted((s.dir / "public").rglob("*.html")):
            html = page.read_text(encoding="utf-8")
            if 'http-equiv="refresh"' in html:
                continue
            self.assertIn('<link rel="manifest" href="/manifest.webmanifest">', html, page)
            self.assertIn('<link rel="apple-touch-icon" href="/app/apple-touch-icon.png">', html, page)
            self.assertRegex(html, r'<script src="/app\.js\?v=[0-9a-f]{8}" defer></script>', page)
        off = s.read("sin-conexion/index.html")
        self.assertIn("<h1>Sin conexión</h1>", off)
        self.assertIn('<meta name="robots" content="noindex, follow">', off)
        self.assertIn('href="tel:+34600000000"', off, "sin conexión, al menos se puede llamar")
        self.assertIn("<h1>You're offline</h1>", s.read("en/offline/index.html"))
        self.assertNotIn("sin-conexion", s.read("sitemap.xml"))
        self.assertIn("<strong>Web instalable.</strong>", s.read("privacidad/index.html"))
        sw = s.read("sw.js")
        pre = json.loads(re.search(r"const PRECACHE = (\[.*?\]);", sw).group(1))
        for u in pre:
            path = u.split("?")[0]
            target = s.dir / "public" / path.lstrip("/")
            self.assertTrue((target / "index.html").exists() if path.endswith("/") else target.exists(), f"precarga de algo que no existe: {u}")
        self.assertIn("/sin-conexion/", pre)
        self.assertIn("/en/offline/", pre)
        self.assertEqual(json.loads(re.search(r"const OFFLINE = (\{.*?\});", sw).group(1)), {"": "/sin-conexion/", "/en/": "/en/offline/"})
        code, out = s.check()
        self.assertEqual(code, 0, out)

    def test_sin_iconos_de_la_medida_justa_no_se_publica(self):
        s = self.site(with_icons=False, app=app_cfg())
        icons(s, skip="app/icono-maskable-512.png")
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("static/app/icono-maskable-512.png", out)
        self.assertIn("python tools/iconos.py", out)
        s2 = self.site(with_icons=False, app=app_cfg())
        icons(s2, wrong="app/apple-touch-icon.png")
        code, out = s2.build()
        self.assertNotEqual(code, 0)
        self.assertIn("apple-touch-icon.png (180×180 px) — mide 188x180", out)
        s3 = self.site(app=app_cfg(nombre_corto="Panadería La Espiga"))
        code, out = s3.build()
        self.assertNotEqual(code, 0)
        self.assertIn("12 caracteres", out)

    def test_service_worker_nueva_version_con_cada_cambio(self):
        s = self.site(app=app_cfg())
        self.ok(s)
        v1 = re.search(r'const VERSION = "(\w+)"', s.read("sw.js")).group(1)
        self.ok(s)
        self.assertEqual(re.search(r'const VERSION = "(\w+)"', s.read("sw.js")).group(1), v1, "misma web, misma versión")
        p = s.dir / "content" / "es" / "sobre.md"
        p.write_text(p.read_text(encoding="utf-8") + "\nUn párrafo nuevo.\n", encoding="utf-8")
        self.ok(s)
        self.assertNotEqual(re.search(r'const VERSION = "(\w+)"', s.read("sw.js")).group(1), v1, "un cambio renueva la copia sin conexión")

    @unittest.skipUnless(shutil.which("node"), "falta Node")
    def test_service_worker_no_toca_formularios_ni_otros_dominios_y_avisos_solo_a_la_web(self):
        s = self.site(products=PRODUCTS, catalog=BUY, app=app_cfg(push={"clave_publica": KEY}))
        self.ok(s)
        harness = r"""
const sw = require("fs").readFileSync(process.argv[2], "utf8");
const h = {}, shown = [], opened = [], responded = [];
const self = { location: { origin: "https://www.ejemplo-cliente.es" }, addEventListener: (t, f) => { h[t] = f; },
  registration: { showNotification: (t, o) => { shown.push({ t, o }); return Promise.resolve(); } },
  clients: { matchAll: () => Promise.resolve([]), openWindow: (u) => { opened.push(u); return Promise.resolve(); }, claim: () => Promise.resolve() },
  skipWaiting: () => Promise.resolve() };
const puts = [];
const caches = { match: () => Promise.resolve(undefined), keys: () => Promise.resolve([]),
  open: () => Promise.resolve({ put: (req) => { puts.push(req.url); return Promise.resolve(); }, keys: () => Promise.resolve([]), delete: () => Promise.resolve() }) };
// La «red»: respuestas por ruta para ver qué se guarda en la copia.
const res = (o) => ({ status: 200, type: "basic", redirected: false, headers: { get: () => "" }, clone() { return this; }, ...o });
const net = { "/ok/": res({}), "/redirigida/": res({ redirected: true }), "/privada/": res({ headers: { get: (h) => h === "cache-control" ? "no-store" : "" } }),
  "/error/": res({ status: 500 }), "/img/a.webp": res({}) };
const fetchStub = (req) => { const r = net[new URL(req.url).pathname]; return r ? Promise.resolve(r) : Promise.reject(new Error("sin red")); };
new Function("self", "caches", "fetch", sw)(self, caches, fetchStub);
const pending = [];
const ev = (req) => ({ request: req, respondWith: (p) => { responded.push(req.url); pending.push(Promise.resolve(p).catch(() => {})); }, waitUntil: (p) => pending.push(p) });
h.fetch(ev({ method: "POST", url: "https://www.ejemplo-cliente.es/contacto/", mode: "navigate" }));
h.fetch(ev({ method: "GET", url: "https://api.cliente.es/api/catalogo/hogaza", mode: "cors" }));
h.fetch(ev({ method: "GET", url: "https://www.googletagmanager.com/gtag/js", mode: "no-cors" }));
h.fetch(ev({ method: "GET", url: "https://www.ejemplo-cliente.es/style.css", mode: "no-cors" }));
const push = (n) => { const p = []; h.push({ data: { json: () => ({ web_push: 8030, notification: n }) }, waitUntil: (x) => p.push(x) }); return Promise.all(p); };
const click = (url) => { const p = []; h.notificationclick({ notification: { data: { url }, close() {} }, waitUntil: (x) => p.push(x) }); return Promise.all(p); };
(async () => {
  const nav = (path) => h.fetch(ev({ method: "GET", url: "https://www.ejemplo-cliente.es" + path, mode: "navigate" }));
  ["/ok/", "/redirigida/", "/privada/", "/error/", "/ok/?pedido=123"].forEach(nav);
  h.fetch(ev({ method: "GET", url: "https://www.ejemplo-cliente.es/img/a.webp", mode: "no-cors" }));
  for (let i = 0; i < 5; i++) await Promise.all(pending.splice(0));
  await push({ title: "Pedido listo", body: "2 × Hogaza", navigate: "https://phishing.example/login" });
  await push({ title: "Reserva", body: "Mañana", navigate: "https://api.cliente.es/api/reservas/gestion/ABC123?t=x" });
  await push({ title: "x".repeat(300), body: "y", navigate: "javascript:alert(1)" });
  await click("https://phishing.example/");
  await click("https://www.ejemplo-cliente.es/cuenta/");
  console.log(JSON.stringify({ responded: responded.filter((u) => !/\/(ok|redirigida|privada|error)\/|a\.webp/.test(u)),
    shown: shown.map((s) => [s.t.length, s.o.data.url, s.o.icon]), opened, puts }));
})();
"""
        js = s.dir / "harness.js"
        js.write_text(harness, encoding="utf-8")
        r = subprocess.run(["node", str(js), str(s.dir / "public" / "sw.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["responded"], ["https://www.ejemplo-cliente.es/style.css"], "ni formularios, ni la API, ni otros dominios")
        self.assertEqual(res["shown"][0][1], "https://www.ejemplo-cliente.es/", "un aviso no abre otra web")
        self.assertEqual(res["shown"][1][1], "https://api.cliente.es/api/reservas/gestion/ABC123?t=x", "sí la API del cliente")
        self.assertEqual(res["shown"][2][:2], [80, "https://www.ejemplo-cliente.es/"])
        self.assertEqual(res["shown"][0][2], "/app/icono-192.png")
        self.assertEqual(res["opened"], ["https://www.ejemplo-cliente.es/", "https://www.ejemplo-cliente.es/cuenta/"])
        self.assertEqual(sorted(res["puts"]), ["https://www.ejemplo-cliente.es/img/a.webp", "https://www.ejemplo-cliente.es/ok/"],
                         "solo se guarda lo completo y sin redirecciones, ni privado, ni errores, ni direcciones con datos (?pedido=)")

    def test_avisos_casilla_sin_marcar_baja_y_privacidad(self):
        s = self.site(products=PRODUCTS, catalog=BUY, app=app_cfg(push={"clave_publica": KEY, "aviso_version": "push-v3"}))
        self.ok(s)
        ficha = s.read("productos/hogaza/index.html")
        box = re.search(r'<div class="push-opt" data-push[^>]*hidden>(.*?)</div>', ficha, re.S)
        self.assertTrue(box, "oculta hasta que app.js sabe que el navegador puede")
        self.assertIn('<input type="checkbox" name="consent_push" value="yes">', box.group(1))
        self.assertNotRegex(box.group(1), r"consent_push[^>]*checked", "nunca marcada")
        self.assertIn('<input type="hidden" name="aviso_push" value="push-v3">', box.group(1))
        self.assertIn('<input type="hidden" name="push_suscripcion" value="">', box.group(1))
        self.assertIn(f'data-key="{KEY}" data-api="https://api.cliente.es"', ficha)
        priv = s.read("privacidad/index.html")
        self.assertIn("<strong>Avisos en este dispositivo.</strong>", priv)
        self.assertIn("que no puede leerlo", priv)
        self.assertRegex(priv, r'<div class="push-off" data-push-baja[^>]*hidden><p><button type="button" class="btn btn-ghost">Dejar de recibir avisos en este dispositivo</button>')
        self.assertIn("<strong>Notifications on this device.</strong>", s.read("en/privacy/index.html"))
        self.assertEqual(s.check()[0], 0)

    def test_avisos_mal_configurados_paran_la_web(self):
        cases = [
            (dict(app=app_cfg(push={"clave_publica": "abc"})), "clave_publica"),
            (dict(app=app_cfg(push={"clave_publica": base64.urlsafe_b64encode(b"\x02" + b"x" * 64).decode().rstrip("=")})), "clave_publica"),
            (dict(app=app_cfg(pwa=False, push={"clave_publica": KEY})), "necesita app.pwa"),
            (dict(app=app_cfg(push={"clave_publica": KEY})), "app.push.api"),
            (dict(app=app_cfg(push={"clave_publica": KEY, "aviso_version": 'v1"><script>'})), "aviso_version"),
        ]
        for cfg, msg in cases:
            with self.subTest(msg=msg):
                s = self.site(**cfg)
                code, out = s.build()
                self.assertNotEqual(code, 0)
                self.assertIn(msg, out)

    def test_enlaces_con_las_apps_well_known(self):
        s = self.site(app=app_cfg(pwa=False, ios={"app_id": "ABCDE12345.es.cliente.app", "rutas": ["/productos/*", "/cuenta/*"], "excluir": ["/blog/*"]},
                                  android={"paquete": "es.cliente.app", "huellas": [FP.lower()]}))
        self.ok(s)
        aasa = json.loads(s.read(".well-known/apple-app-site-association"))
        det = aasa["applinks"]["details"][0]
        self.assertEqual(det["appIDs"], ["ABCDE12345.es.cliente.app"])
        self.assertEqual(det["components"][0], {"/": "/blog/*", "exclude": True}, "las exclusiones van primero")
        self.assertEqual([c["/"] for c in det["components"][1:]], ["/productos/*", "/cuenta/*"])
        al = json.loads(s.read(".well-known/assetlinks.json"))
        self.assertEqual(al[0]["relation"], ["delegate_permission/common.handle_all_urls"])
        self.assertEqual(al[0]["target"], {"namespace": "android_app", "package_name": "es.cliente.app", "sha256_cert_fingerprints": [FP]})
        self.assertFalse((s.dir / "public" / ".well-known" / ".htaccess").exists())
        s2 = self.site(app=app_cfg(pwa=False, ios={"app_id": "ABCDE12345.es.cliente.app"}), redirecciones={"htaccess": True, "reglas": {}})
        self.ok(s2)
        self.assertIn("ForceType application/json", s2.read(".well-known/.htaccess"))
        self.assertEqual(json.loads(s2.read(".well-known/apple-app-site-association"))["applinks"]["details"][0]["components"], [{"/": "/*"}])
        self.assertEqual(s.check()[0], 0)

    def test_datos_de_las_apps_no_validos_paran_la_web(self):
        cases = [
            (dict(ios={"app_id": "es.cliente.app"}), "app.ios.app_id"),
            (dict(ios={"app_id": "ABCDE12345.es.cliente.app", "rutas": ["productos/*"]}), "rutas"),
            (dict(ios={"app_id": "ABCDE12345.es.cliente.app", "rutas": ['/x"}']}), "rutas"),
            (dict(ios={"app_store_id": "id123"}), "app_store_id"),
            (dict(android={"paquete": "es.cliente.app"}), "huellas"),
            (dict(android={"paquete": "es.cliente.app", "huellas": ["AB:CD"]}), "32 pares"),
            (dict(android={"paquete": "1es"}), "paquete"),
            (dict(android={"huellas": [FP]}), "huellas sin paquete"),
            (dict(tiendas={"ios": "https://apps.apple.com.ejemplo.com/es/app/id123456789"}), "tiendas.ios"),
            (dict(tiendas={"android": "https://play.google.com.evil/store/apps/details?id=es.x"}), "tiendas.android"),
            (dict(tiendas={"android": "http://play.google.com/store/apps/details?id=es.x"}), "tiendas.android"),
        ]
        for over, msg in cases:
            with self.subTest(msg=msg, over=over):
                s = self.site(app=app_cfg(pwa=False, **over))
                code, out = s.build()
                self.assertNotEqual(code, 0, over)
                self.assertIn(msg, out)

    def test_tiendas_pie_banner_y_privacidad_con_firebase(self):
        stores = {"ios": "https://apps.apple.com/es/app/la-espiga/id123456789", "android": "https://play.google.com/store/apps/details?id=es.cliente.app"}
        enc = [{"servicio": "alojamiento", "nombre": "Proveedor", "pais": "España"}]
        s = self.site(app=app_cfg(tiendas=stores, ios={"app_store_id": "123456789"}, android={"paquete": "es.cliente.app", "huellas": [FP]}),
                      privacidad={"encargados": enc})
        self.ok(s)
        home = s.read("index.html")
        self.assertIn('<meta name="apple-itunes-app" content="app-id=123456789">', home)
        self.assertIn(f'<li><a href="{stores["ios"]}" rel="noopener">App para iPhone (App Store)</a></li>', home)
        self.assertIn(f'<li><a href="{stores["android"]}" rel="noopener">App para Android (Google Play)</a></li>', home)
        self.assertEqual(json.loads(s.read("manifest.webmanifest"))["related_applications"],
                         [{"platform": "play", "url": stores["android"], "id": "es.cliente.app"}])
        self.assertNotIn("prefer_related_applications", s.read("manifest.webmanifest"), "la web sigue siendo instalable")
        priv = s.read("privacidad/index.html")
        self.assertIn("<strong>App para móvil.</strong>", priv)
        self.assertIn("Firebase Cloud Messaging", priv)
        r = subprocess.run([sys.executable, "-B", "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
        self.assertIn("sin el servicio «notificaciones»", r.stdout)
        s2 = self.site(app=app_cfg(tiendas=stores), privacidad={"encargados": enc + [{"servicio": "notificaciones", "nombre": "Google Ireland Limited (Firebase)", "pais": "Irlanda"}]})
        self.ok(s2)
        r2 = subprocess.run([sys.executable, "-B", "tools/check.py", "--release"], cwd=s2.dir, capture_output=True, text=True)
        self.assertNotIn("«notificaciones»", r2.stdout)
        self.assertIn("avisos en la app (Firebase Cloud Messaging) (Google Ireland Limited (Firebase), Irlanda)", s2.read("privacidad/index.html"))

    def test_archivos_ocultos_de_static_no_se_publican(self):
        s = self.site(app=app_cfg(pwa=False, android={"paquete": "es.cliente.app", "huellas": [FP]}))
        (s.dir / "static" / ".DS_Store").write_text("x")
        (s.dir / "static" / ".env").write_text("SECRETO=1")
        self.ok(s)
        hidden = sorted(str(p.relative_to(s.dir / "public")) for p in (s.dir / "public").rglob(".*"))
        self.assertEqual(hidden, [".well-known"], "solo lo que genera build.py")

    def test_check_detecta_manifiesto_roto_y_well_known_ilegible(self):
        s = self.site(app=app_cfg(android={"paquete": "es.cliente.app", "huellas": [FP]}))
        self.ok(s)
        m = s.dir / "public" / "manifest.webmanifest"
        d = json.loads(m.read_text())
        d["icons"] = [i for i in d["icons"] if i["purpose"] != "maskable"]
        d["start_url"] = "https://otra-web.example/"
        m.write_text(json.dumps(d))
        (s.dir / "public" / ".well-known" / "assetlinks.json").write_text("{roto")
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("ERROR: manifest.webmanifest: falta el icono maskable", out)
        self.assertIn("ERROR: manifest.webmanifest: start_url fuera de la web", out)
        self.assertIn("ERROR: .well-known/assetlinks.json: JSON no válido", out, "es un error, no un aviso")

    @unittest.skipUnless(HAS_PIL, "falta Pillow")
    def test_iconos_desde_un_png(self):
        from PIL import Image
        s = self.site(with_icons=False)
        src = s.dir / "simbolo.png"
        Image.new("RGBA", (800, 800), (0, 0, 0, 0)).save(src)
        im = Image.open(src)
        im.paste((154, 75, 28, 255), (200, 200, 600, 600))
        im.save(src)
        r = subprocess.run([sys.executable, "-B", "tools/iconos.py", str(src), "--fondo", "#FBF7F2"], cwd=s.dir, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        sizes = {p.name: Image.open(p).size for p in (s.dir / "static" / "app").glob("*.png")}
        self.assertEqual(sizes, {"icono-192.png": (192, 192), "icono-512.png": (512, 512), "icono-maskable-512.png": (512, 512), "apple-touch-icon.png": (180, 180)})
        apple = Image.open(s.dir / "static" / "app" / "apple-touch-icon.png")
        self.assertEqual(apple.mode, "RGB", "sin transparencia (iOS la pinta de negro)")
        from PIL import ImageChops
        mask = Image.open(s.dir / "static" / "app" / "icono-maskable-512.png").convert("RGB")
        bbox = ImageChops.difference(mask, Image.new("RGB", mask.size, mask.getpixel((0, 0)))).getbbox()
        inner = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / 512
        self.assertLessEqual(inner, 0.566, "el símbolo cabe en la zona segura (círculo del 80 %)")
        small = s.dir / "pequeno.png"
        Image.new("RGB", (256, 256), (1, 2, 3)).save(small)
        r = subprocess.run([sys.executable, "-B", "tools/iconos.py", str(small)], cwd=s.dir, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("512 px", r.stdout + r.stderr)

    def test_github_pages_publica_well_known(self):
        flujo = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
        paso = re.search(r"uses: actions/upload-pages-artifact@(\w+).*?\n((?:\s+.*\n)+?)\s+- id: deployment", flujo, re.S)
        self.assertTrue(paso)
        self.assertRegex(paso.group(2), r"include-hidden-files:\s*true", "sin esto, GitHub Pages no publica /.well-known (enlaces con las apps)")


@unittest.skipUnless(HAS_PW, "falta Playwright")
class AppNavegador(unittest.TestCase):
    """En Chromium, con la web servida en 127.0.0.1 (contexto seguro: el service worker funciona)."""

    @classmethod
    def setUpClass(cls):
        import functools
        import http.server
        import threading
        cls.s = Site(products=PRODUCTS, catalog=BUY, app=app_cfg(push={"clave_publica": KEY}))
        icons(cls.s)
        code, out = cls.s.build()
        assert code == 0, out

        class Quiet(http.server.SimpleHTTPRequestHandler):
            extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".webmanifest": "application/manifest+json", ".js": "text/javascript"}

            def log_message(self, *a):
                pass
        cls.Quiet = Quiet
        cls.srv, cls.url = cls.serve()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def serve(cls):
        import functools
        import http.server
        import threading
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(cls.Quiet, directory=str(cls.s.dir / "public")))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, f"http://127.0.0.1:{srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.s.cleanup()

    def page(self, permiso="granted", subscription=None):
        ctx = self.browser.new_context(locale="es-ES")
        sub = subscription or {"endpoint": "https://fcm.googleapis.com/fcm/send/prueba", "expirationTime": None, "keys": {"p256dh": KEY, "auth": "BTBZMqHH6r4Tts7J_aSIgg"}}
        ctx.add_init_script(f"""
            Notification.requestPermission = () => Promise.resolve({json.dumps(permiso)});
            window.__unsub = 0;
            const fake = {{ endpoint: {json.dumps(sub["endpoint"])}, toJSON: () => ({json.dumps(sub)}), unsubscribe: () => {{ window.__unsub++; return Promise.resolve(true); }} }};
            PushManager.prototype.getSubscription = function () {{ return Promise.resolve(window.__tiene ? fake : null); }};
            PushManager.prototype.subscribe = function (o) {{ window.__clave = o.applicationServerKey.byteLength; window.__tiene = true; return Promise.resolve(fake); }};
        """)
        ctx.route("https://api.cliente.es/**", lambda r: r.fulfill(status=200, body='{"ok":true}', headers={"access-control-allow-origin": "*"}))
        p = ctx.new_page()
        errors = []
        p.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        p.on("pageerror", lambda e: errors.append(str(e)))
        return ctx, p, errors

    def install_sw(self, p) -> None:
        """Registra el service worker y espera a que se active; si no se instala (precarga rota), falla en 10 s en vez de colgarse."""
        p.evaluate("Promise.race([navigator.serviceWorker.register('/sw.js').then(() => navigator.serviceWorker.ready), "
                   "new Promise((_, no) => setTimeout(() => no(new Error('el service worker no se instala')), 10000))])")

    def registered(self, p) -> bool:
        return p.evaluate("navigator.serviceWorker.getRegistration('/').then(r => !!r)")

    def test_solo_visitar_no_registra_nada_y_la_casilla_pide_el_permiso_al_marcarla(self):
        ctx, p, errors = self.page()
        enviados = []
        ctx.route("https://api.cliente.es/api/checkout", lambda r: (enviados.append(r.request.post_data), r.fulfill(status=200, body="{}")))
        p.goto(self.url + "/productos/hogaza/")
        box = p.locator("form.buy [data-push]")
        box.wait_for()
        p.wait_for_timeout(300)
        self.assertFalse(self.registered(p), "a quien solo visita la web no se le registra nada")
        cb = box.locator("input[name=consent_push]")
        self.assertFalse(cb.is_checked())
        cb.check()
        p.wait_for_function("document.querySelector('input[name=push_suscripcion]').value !== ''")
        self.assertEqual(p.evaluate("window.__clave"), 65)
        self.assertTrue(self.registered(p), "al pedir avisos, sí")
        sent = json.loads(p.locator("input[name=push_suscripcion]").input_value())
        self.assertEqual(sent["endpoint"], "https://fcm.googleapis.com/fcm/send/prueba")
        p.locator("form.buy button[type=submit]").click()
        p.wait_for_timeout(500)
        self.assertTrue(enviados and "push_suscripcion=" in enviados[0] and "consent_push=yes" in enviados[0], enviados)
        self.assertEqual(errors, [])
        ctx.close()

    def test_permiso_bloqueado_desmarca_y_lo_dice(self):
        ctx, p, errors = self.page(permiso="denied")
        p.goto(self.url + "/productos/hogaza/")
        cb = p.locator("form.buy input[name=consent_push]")
        cb.wait_for()
        cb.click()
        p.locator(".push-msg:not(:empty)").wait_for()
        self.assertFalse(cb.is_checked())
        self.assertIn("bloqueados en este navegador", p.locator(".push-msg").inner_text())
        self.assertEqual(p.evaluate("document.activeElement.name"), "consent_push", "el foco vuelve a la casilla")
        self.assertEqual(p.locator("input[name=push_suscripcion]").input_value(), "")
        self.assertEqual(errors, [])
        ctx.close()

    def test_sin_conexion_copia_de_lo_visitado_y_pagina_sin_conexion(self):
        # Un servidor propio que se apaga: la emulación «sin conexión» de Chromium no afecta al service worker.
        srv, url = self.serve()
        ctx, p, errors = self.page()
        p.goto(url + "/")
        self.install_sw(p)
        p.reload()
        p.wait_for_function("!!navigator.serviceWorker.controller")
        p.goto(url + "/sobre/")
        p.wait_for_timeout(300)
        srv.shutdown()
        srv.server_close()
        p.goto(url + "/sobre/")
        self.assertEqual(p.locator("h1").inner_text(), "Sobre nosotros", "lo visitado se ve sin conexión")
        p.goto(url + "/blog/")
        self.assertEqual(p.locator("h1").inner_text(), "Sin conexión", "lo no visitado: «Sin conexión», con el teléfono")
        self.assertTrue(p.locator('a[href^="tel:"]').count())
        p.goto(url + "/en/about/")
        self.assertEqual(p.locator("h1").inner_text(), "You're offline")
        self.assertEqual(errors, [])
        ctx.close()

    def test_dejar_de_recibir_avisos_en_la_privacidad(self):
        ctx, p, errors = self.page()
        bajas = []
        ctx.route("https://api.cliente.es/api/push/baja", lambda r: (bajas.append(json.loads(r.request.post_data)), r.fulfill(status=200, body='{"ok":true}',
                  headers={"access-control-allow-origin": "*"})))
        p.goto(self.url + "/privacidad/")
        p.wait_for_timeout(300)
        self.assertTrue(p.locator("[data-push-baja]").is_hidden(), "sin avisos activos no se enseña")
        p.evaluate("window.__tiene = true")
        self.install_sw(p)
        p.add_init_script("window.__tiene = true;")
        p.reload()
        btn = p.locator("[data-push-baja] button")
        btn.wait_for()
        btn.click()
        p.locator("[data-push-baja] [role=status]:not(:empty)").wait_for()
        self.assertEqual(bajas, [{"endpoint": "https://fcm.googleapis.com/fcm/send/prueba"}])
        self.assertEqual(p.evaluate("window.__unsub"), 1, "y el navegador anula la suscripción")
        self.assertIn("ya no recibirá avisos", p.locator("[data-push-baja] [role=status]").inner_text())
        self.assertEqual(errors, [])
        ctx.close()

    def test_axe_en_la_ficha_con_la_casilla_y_en_sin_conexion(self):
        axe = ROOT / "node_modules" / "axe-core" / "axe.min.js"
        if not axe.exists():
            self.skipTest("falta axe-core (npm ci)")
        ctx, p, errors = self.page()
        found = []
        for u in ("/productos/hogaza/", "/sin-conexion/", "/privacidad/"):
            p.goto(self.url + u)
            if u.startswith("/productos/"):
                p.locator("[data-push]").wait_for(state="visible")  # axe revisa también la casilla de avisos
            p.wait_for_timeout(200)
            p.add_script_tag(content=axe.read_text(encoding="utf-8"))
            v = p.evaluate("axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}).then(r => r.violations.map(x => x.id))")
            found += [f"{u} {x}" for x in v]
        self.assertEqual(found, [])
        self.assertEqual(errors, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
