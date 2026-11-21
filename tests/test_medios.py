"""Fotos y vídeo (skill fotografia-video-cliente).

Protecciones con test: cada foto propia lleva width y height (la página no salta) y, si hay variantes, srcset y sizes según dónde va;
un vídeo propio solo se publica con portada, título, controles, sin reproducción automática, cargando bajo demanda y con subtítulos
WebVTT (o «sin_voz»); más de 30 MB no se publica; con YouTube, una imagen propia que enlaza (nada se carga de Google); un <video>
escrito a mano sin subtítulos hace fallar check.py; tools/images.py y tools/video.py quitan GPS y demás metadatos.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_build import PRODUCTS, ROOT, Site

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

VTT = "WEBVTT\n\n00:00.000 --> 00:03.000\nAsí empieza el día en el obrador.\n"
PNG_1x1 = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000280000001e00806000000") + b"\x00" * 64  # cabecera de un PNG de 640x480


class Medios(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, body: str, files: dict | None = None, **cfg) -> Site:
        s = Site(products=PRODUCTS, **cfg)
        self.sites.append(s)
        for rel, data in (files or {}).items():
            p = s.dir / "static" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, int):
                with open(p, "wb") as fh:
                    fh.truncate(data)  # archivo del tamaño pedido (sin escribir los bytes)
            else:
                p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        (s.dir / "content" / "es" / "obrador.md").write_text(f"---\ntitle: El obrador\ndescription: Cómo trabajamos.\n---\n\n{body}\n", encoding="utf-8")
        return s

    def video(self, extra: str = "", files: dict | None = None, **cfg):
        base = {"video/horno.mp4": b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100, "img/horno.png": PNG_1x1, "video/horno.es.vtt": VTT}
        base.update(files or {})
        body = f":::video\ntitulo: Así hacemos la hogaza\narchivo: video/horno.mp4\nposter: img/horno.png\nsubtitulos: video/horno.es.vtt\n{extra}:::"
        return self.site(body, {k: v for k, v in base.items() if v is not None}, **cfg)

    # ---------------------------------------------------------------- fotos
    @unittest.skipUnless(HAS_PIL, "falta Pillow")
    def test_fotos_con_medidas_y_variantes(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            for name, size, fmt in (("obrador.webp", (1600, 1067), "WEBP"), ("obrador-480.webp", (480, 320), "WEBP"),
                                    ("obrador-960.webp", (960, 640), "WEBP"), ("horno.jpg", (1200, 900), "JPEG"),
                                    ("masa.png", (700, 525), "PNG"), ("sin-perdida.webp", (333, 222), "WEBP_LOSSLESS"),
                                    ("alfa.webp", (321, 123), "WEBP"), ("cartel.webp", (800, 600), "WEBP"),
                                    ("cartel-2026.webp", (1200, 900), "WEBP")):  # otra foto con un año en el nombre, no una variante
                im = Image.new("RGBA" if name == "alfa.webp" else "RGB", size, (150, 90, 40, 128))  # con transparencia: WebP «VP8X»
                im.save(tmp / name, "WEBP", lossless=True) if fmt == "WEBP_LOSSLESS" else im.save(tmp / name, fmt)
            files = {f"img/{p.name}": p.read_bytes() for p in tmp.iterdir()}
        finally:
            shutil.rmtree(tmp)
        body = ("![Masa madre fermentando](/img/obrador.webp)\n\n![Horno de leña](/img/horno.jpg)\n\n![Masa](/img/masa.png)\n\n"
                "![Pan](/img/sin-perdida.webp)\n\n![Sello](/img/alfa.webp)\n\n![Cartel](/img/cartel.webp)\n\n![Fuera](https://cdn.ejemplo.es/x.webp)\n\n"
                ":::cards\n## Lo nuestro\n### Hogaza\n![Hogaza](/img/obrador.webp)\nDe trigo.\n:::")
        s = self.site(body, files, privacidad={"encargados": [{"servicio": "otro", "nombre": "CDN", "pais": "España", "dominios": ["cdn.ejemplo.es"]}]})
        code, out = s.build()
        self.assertEqual(code, 0, out)
        h = s.read("obrador/index.html")
        self.assertIn('alt="Masa madre fermentando" src="/img/obrador.webp" width="1600" height="1067" '
                      'srcset="/img/obrador-480.webp 480w, /img/obrador-960.webp 960w, /img/obrador.webp 1600w" sizes="(max-width: 46rem) 100vw, 46rem"', h)
        self.assertIn('alt="Horno de leña" src="/img/horno.jpg" width="1200" height="900"', h)
        self.assertIn('alt="Masa" src="/img/masa.png" width="700" height="525"', h)
        self.assertIn('alt="Pan" src="/img/sin-perdida.webp" width="333" height="222"', h)
        self.assertIn('alt="Sello" src="/img/alfa.webp" width="321" height="123"', h)
        self.assertIn('alt="Cartel" src="/img/cartel.webp" width="800" height="600" />', h, "una «variante» más grande no es una variante: sin srcset")
        self.assertIn('sizes="(max-width: 52rem) 100vw, 24rem"', h, "en tarjetas, un tercio")
        self.assertNotRegex(h, r'cdn\.ejemplo\.es/x\.webp"[^>]*width=', "lo de fuera no se toca")

    # ---------------------------------------------------------------- vídeo propio
    def test_video_propio_accesible_y_sin_reproduccion_automatica(self):
        s = self.video()
        code, out = s.build()
        self.assertEqual(code, 0, out)
        h = s.read("obrador/index.html")
        self.assertIn('<video controls preload="none" playsinline poster="/img/horno.png" width="640" height="480" aria-label="Así hacemos la hogaza">', h)
        self.assertIn('<source src="/video/horno.mp4" type="video/mp4">', h)
        self.assertIn('<track kind="captions" src="/video/horno.es.vtt" srclang="es" label="Español" default>', h)
        self.assertIn("<figcaption>Así hacemos la hogaza</figcaption>", h)
        self.assertNotIn("autoplay", h)
        code, out = s.check()
        self.assertEqual(code, 0, out)

    def test_sin_subtitulos_no_se_publica_salvo_sin_voz(self):
        s = self.video(files={"video/horno.es.vtt": None})
        body = (s.dir / "content/es/obrador.md").read_text(encoding="utf-8")
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("no existe static/video/horno.es.vtt", out)  # la línea está pero el archivo no
        (s.dir / "content/es/obrador.md").write_text(body.replace("subtitulos: video/horno.es.vtt\n", ""), encoding="utf-8")
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("sin «subtitulos:»", out)
        s2 = self.video("sin_voz: true\n", files={"video/horno.es.vtt": None})
        (s2.dir / "content/es/obrador.md").write_text((s2.dir / "content/es/obrador.md").read_text(encoding="utf-8")
                                                        .replace("subtitulos: video/horno.es.vtt\n", ""), encoding="utf-8")
        code, out = s2.build()
        self.assertEqual(code, 0, out)
        self.assertIn("data-sin-voz", s2.read("obrador/index.html"))
        self.assertEqual(s2.check()[0], 0)

    def test_vtt_raro_portada_que_falta_y_peso(self):
        s = self.video(files={"video/horno.es.vtt": "1\n00:00:00,000 --> 00:00:02,000\nesto es SRT\n"})
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("no es WebVTT", out)
        s = self.video(files={"img/horno.png": None})
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("no existe static/img/horno.png", out)
        s = self.video(files={"video/horno.mp4": 31_000_000})
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("más de 30 MB no se sirve desde la web", out)
        s = self.video(files={"video/horno.mp4": 16_000_000})
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertIn("AVISO", out)

    def test_bloque_mal_escrito(self):
        for extra, msg in (("autoplay: true\n", "línea no válida"), ("archivo2: x\n", "línea no válida")):
            code, out = self.video(extra).build()
            self.assertNotEqual(code, 0)
            self.assertIn(msg, out)
        s = self.site(":::video\narchivo: video/horno.mp4\nposter: img/horno.png\nsin_voz: true\n:::",
                      {"video/horno.mp4": b"\x00" * 10, "img/horno.png": PNG_1x1})
        code, out = s.build()
        self.assertIn("sin «titulo:»", out)
        code, out = self.video("transcripcion: obrador-texto\n").build()
        self.assertIn("«transcripcion:» es la clave", out)

    def test_transcripcion_enlazada(self):
        s = self.video("transcripcion: @sobre\n")
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertRegex(s.read("obrador/index.html"), r'<figcaption>Así hacemos la hogaza · <a href="/sobre[^"]*">Texto del vídeo</a></figcaption>')

    # ---------------------------------------------------------------- YouTube sin cargar nada de Google
    def test_youtube_como_imagen_que_enlaza(self):
        s = self.site(":::video\ntitulo: La masa madre\nyoutube: dQw4w9WgXcQ\nposter: img/horno.png\n:::", {"img/horno.png": PNG_1x1})
        code, out = s.build()
        self.assertEqual(code, 0, out)
        h = s.read("obrador/index.html")
        self.assertIn('<a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ" rel="noopener">', h)
        self.assertIn('alt="Ver el vídeo «La masa madre» en YouTube"', h)
        self.assertNotRegex(h, r"<iframe|youtube-nocookie|ytimg|<script[^>]+youtube")
        self.assertEqual(s.check()[0], 0, s.check()[1])
        for bad in ("youtube: https://youtu.be/dQw4w9WgXcQ", "youtube: dQw4w9WgXcQ\narchivo: video/horno.mp4"):
            s = self.site(f":::video\ntitulo: X\n{bad}\nposter: img/horno.png\n:::", {"img/horno.png": PNG_1x1, "video/horno.mp4": b"\x00"})
            code, out = s.build()
            self.assertNotEqual(code, 0, bad)

    # ---------------------------------------------------------------- vídeo escrito a mano
    def test_video_a_mano_sin_subtitulos_falla_en_check(self):
        s = self.site('<video controls src="/video/horno.mp4"></video>', {"video/horno.mp4": b"\x00"})
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("<video> sin subtítulos", out)
        s2 = self.site('<video controls data-sin-voz src="/video/horno.mp4"></video>', {"video/horno.mp4": b"\x00"})
        self.assertEqual(s2.build()[0], 0)
        self.assertNotIn("sin subtítulos", s2.check()[1])


@unittest.skipUnless(HAS_PIL, "falta Pillow")
class HerramientaFotos(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "tools/images.py"), *args], capture_output=True, text=True)

    def foto(self, name="Foto Móvil.jpg", size=(3000, 2000)):
        im = Image.new("RGB", size, (180, 120, 60))
        ex = Image.Exif()
        ex[0x010F], ex[0x0110], ex[0x013B] = "MarcaMovil", "Modelo X", "Nombre Apellido"
        ex[0x8825] = {1: "N", 2: (36.0, 35.0, 12.0), 3: "W", 4: (4.0, 31.0, 5.0)}
        xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description exif:GPSLatitude="36,35N" xmlns:exif="http://ns.adobe.com/exif/1.0/"/></rdf:RDF></x:xmpmeta>'
        p = self.tmp / name
        im.save(p, "JPEG", exif=ex.tobytes(), xmp=xmp)
        return p

    def test_sin_gps_ni_datos_de_camara_y_variantes(self):
        src = self.foto()
        out = self.tmp / "web"
        r = self.run_tool(str(src), str(out), "--variantes", "480,960,4000")
        self.assertEqual(r.returncode, 0, r.stderr)
        names = sorted(p.name for p in out.iterdir())
        self.assertEqual(names, ["foto-movil-480.webp", "foto-movil-960.webp", "foto-movil.webp"], "una variante mayor que la foto no se hace")
        for p in out.iterdir():
            raw = p.read_bytes()
            with Image.open(p) as im:
                self.assertEqual(dict(im.getexif()), {}, p.name)
                self.assertNotIn("xmp", im.info, p.name)
            for needle in (b"GPS", b"MarcaMovil", b"Nombre Apellido", b"Exif"):
                self.assertNotIn(needle, raw, f"{p.name}: {needle!r}")
        with Image.open(out / "foto-movil.webp") as im:
            self.assertEqual(im.size, (1600, 1067))

    def test_recorte_para_compartir(self):
        src = self.foto(size=(2000, 2000))
        r = self.run_tool(str(src), str(self.tmp), "--recorte", "1200x630", "--nombre", "og", "--png")
        self.assertEqual(r.returncode, 0, r.stderr)
        with Image.open(self.tmp / "og.png") as im:
            self.assertEqual(im.size, (1200, 630))
            self.assertEqual(dict(im.getexif()), {})
        self.assertNotEqual(self.run_tool(str(self.tmp), str(self.tmp / "x"), "--nombre", "og").returncode, 0, "--nombre con varias fotos")
        self.assertNotEqual(self.run_tool(str(src), str(self.tmp), "--recorte", "1200").returncode, 0)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "falta ffmpeg")
class HerramientaVideo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_sin_ubicacion_faststart_y_portada(self):
        src = self.tmp / "IMG 0042.mov"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=25:duration=3", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=3", "-metadata", "location=+36.5950-004.5370/", "-metadata", "make=MarcaMovil",
                        "-metadata", "creation_time=2026-10-01T10:00:00Z", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src)], check=True)
        tags = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(src)],
                                         capture_output=True, text=True).stdout)["format"].get("tags", {})
        self.assertTrue(any("location" in k for k in tags), f"el original sí lleva ubicación: {tags}")
        r = subprocess.run([sys.executable, "-B", str(ROOT / "tools/video.py"), str(src), str(self.tmp / "static/video")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mp4 = self.tmp / "static/video/img-0042.mp4"
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(mp4)],
                                         capture_output=True, text=True).stdout)
        tags = info["format"].get("tags", {})
        self.assertFalse(any(k in tags for k in ("location", "location-eng", "com.apple.quicktime.location.ISO6709", "make", "creation_time")), tags)
        raw = mp4.read_bytes()
        self.assertNotIn(b"+36.5950", raw)
        self.assertNotIn(b"MarcaMovil", raw)
        self.assertLess(raw.find(b"moov"), raw.find(b"mdat"), "faststart: el índice va delante")
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        self.assertEqual((v["codec_name"], v["height"], v["pix_fmt"]), ("h264", 720, "yuv420p"))
        self.assertTrue((self.tmp / "static/video/img-0042-poster.webp").is_file())
        self.assertIn("subtitulos: video/img-0042.es.vtt", r.stdout)


if __name__ == "__main__":
    unittest.main()
